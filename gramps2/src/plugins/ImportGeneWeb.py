#
# Gramps - a GTK+/GNOME based genealogy program
#
# Copyright (C) 2000-2004  Martin Hawlisch, Donald N. Allingham
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA
#

# $Id$

"Import from GeneWeb"

#-------------------------------------------------------------------------
#
# standard python modules
#
#-------------------------------------------------------------------------
import os
import re
import string
import const
import time

#-------------------------------------------------------------------------
#
# GTK/GNOME Modules
#
#-------------------------------------------------------------------------
import gtk
import gtk.glade

#-------------------------------------------------------------------------
#
# GRAMPS modules
#
#-------------------------------------------------------------------------
import Errors
import RelLib
import Date
import DateHandler
import latin_utf8 
import Utils
from QuestionDialog import ErrorDialog
from gettext import gettext as _


#-------------------------------------------------------------------------
#
#
#
#-------------------------------------------------------------------------
def importData(database, filename, cb=None):

    global callback

    try:
        g = GeneWebParser(database,filename)
    except IOError,msg:
        ErrorDialog(_("%s could not be opened\n") % filename,str(msg))
        return
    except:
        ErrorDialog(_("%s could not be opened\n") % filename)
        import DisplayTrace
        DisplayTrace.DisplayTrace()
        return

    try:
        status = g.parse_geneweb_file()
    except IOError,msg:
        errmsg = _("%s could not be opened\n") % filename
        ErrorDialog(errmsg,str(msg))
        return
    except:
        import DisplayTrace
        DisplayTrace.DisplayTrace()
        return
    

#-------------------------------------------------------------------------
#
#
#
#-------------------------------------------------------------------------
class GeneWebParser:
    def __init__(self, dbase, file):
        self.db = dbase
        self.f = open(file,"rU")
        self.filename = file
	self.dp = DateHandler.create_parser()

    def get_next_line(self):
        line = self.f.readline()
        if line:
            line = line.strip()
        else:
            line = None
        return line
        
    def parse_geneweb_file(self):
        self.trans = self.db.transaction_begin()
        t = time.time()
        self.index = 0
        self.fam_count = 0
        self.indi_count = 0
        
        self.fkeys = []
        self.ikeys = {}
        self.pkeys = {}
        self.skeys = {}
        
        self.current_mode = None
        self.current_family = None
        self.current_husband_handle = None
        try:
            while 1:
                line = self.get_next_line()
                if line == None:
                    break
                if line == "":
                    continue
                
                fields = line.split(" ")
            
                print "LINE: %s" %line
                if fields[0] == "fam":
                    self.read_family_line(line,fields)
                elif fields[0] == "src":
                    self.read_source_line(line,fields)
                elif fields[0] == "wit":
                    self.read_witness_line(line,fields)
                elif fields[0] == "cbp":
                    self.read_children_birthplace_line(line,fields)
                elif fields[0] == "beg":
                    self.read_children_lines()
                elif fields[0] == "comm":
                    self.read_family_comment(line,fields)
                elif fields[0] == "notes":
                    self.read_notes_lines(line,fields)
                elif fields[0] == "end":
                    self.current_mode = None
                else:
                    print "Token >%s< unknown. line skipped: %s" % (fields[0],line)
        except Errors.GedcomError, err:
            self.errmsg(str(err))
            
        t = time.time() - t
        msg = _('Import Complete: %d seconds') % t

        self.db.transaction_commit(self.trans,_("GeneWeb import"))
        
        print msg
        print "Families: %d" % len(self.fkeys)
        print "Individuals: %d" % len(self.ikeys)
        return None

    def read_family_line(self,line,fields):
        self.current_husband_handle = None
        self.current_family = RelLib.Family()
        self.db.add_family(self.current_family,self.trans)
        self.db.commit_family(self.current_family,self.trans)
        self.fkeys.append(self.current_family.get_handle())
        idx = 1;
        
        print "\nHusband:"
        (idx,husband) = self.parse_person(fields,idx,RelLib.Person.male,None)
        if husband:
            self.current_husband_handle = husband.get_handle()
            self.current_family.set_father_handle(husband.get_handle())
            self.db.commit_family(self.current_family,self.trans)
            husband.add_family_handle(self.current_family.get_handle())
            self.db.commit_person(husband,self.trans)
        print "Marriage:"
        idx = self.parse_marriage(fields,idx)
        print "Wife:"
        (idx,wife) = self.parse_person(fields,idx,RelLib.Person.female,None)
        if wife:
            self.current_family.set_mother_handle(wife.get_handle())
            self.db.commit_family(self.current_family,self.trans)
            wife.add_family_handle(self.current_family.get_handle())
            self.db.commit_person(wife,self.trans)
        return None
    
    def read_source_line(self,line,fields):
        if not self.current_family:
        	print "Unknown family of child!"
        	return None
        source = self.get_or_create_source(self.decode(fields[1]))
        self.current_family.add_source_reference(source)
        self.db.commit_family(self.current_family,self.trans)
        return None
    
    def read_witness_line(self,line,fields):
        print "Witness:"
        if fields[1] == "m:":
            self.parse_person(fields,2,RelLib.Person.male,None)
        elif fields[1] == "f:":
            self.parse_person(fields,2,RelLib.Person.female,None)
        else:
            self.parse_person(fields,1,None,None)
        return None

    def read_children_lines(self):
        father_surname = "Dummy"
        if not self.current_husband_handle:
            print "Unknown father for child!"
            return None
        husb = self.db.get_person_from_handle(self.current_husband_handle)
        father_surname = husb.get_primary_name().get_surname()
        if not self.current_family:
        	print "Unknown family of child!"
        	return None
        while 1:
            line = self.get_next_line()
            if line == None:
                break
            if line == "":
                continue

            fields = line.split(" ")
            if fields[0] == "-":
                print "Child:"
                child = None
                if fields[1] == "h":
                    (idx,child) = self.parse_person(fields,2,RelLib.Person.male,father_surname)
                elif fields[1] == "f":
                    (idx,child) = self.parse_person(fields,2,RelLib.Person.female,father_surname)
                else:
                    (idx,child) = self.parse_person(fields,1,None,father_surname)
                    
                if child:
                    self.current_family.add_child_handle(child.get_handle())
                    self.db.commit_family(self.current_family,self.trans)
                    child.add_parent_family_handle(self.current_family.get_handle(),"Birth","Birth")
                    self.db.commit_person(child,self.trans)
            else:
                break
        return None
            

    def read_children_birthplace_line(self,line,fields):
        return None

    def read_family_comment(self,line,fields):
        if not self.current_family:
        	print "Unknown family of child!"
        	return None
        self.current_family.set_note(self.cnv(line))
        self.db.commit_family(self.current_family,self.trans)
        return None

    def read_notes_lines(self,line,fields):
        (idx,person) = self.parse_person(fields,1,None,None)
        note_txt = ""
        while 1:
            line = self.get_next_line()
            if line == None:
                break

            fields = line.split(" ")
            if fields[0] == "end" and fields[1] == "notes":
                break
            elif fields[0] == "beg":
                continue
            else:
                if note_txt:
                    note_txt = note_txt + "\n" + self.cnv(line)
                else:
                    note_txt = note_txt + self.cnv(line)
        if note_txt:
            person.set_note(note_txt)
            self.db.commit_person(person,self.trans)
        return None
    
    def parse_marriage(self,fields,idx):
        mdate = self.parse_date(fields[idx])
        mariageDataRe = re.compile("^[+#-0-9].*$")

        mar_date = None
        mar_place = None
        mar_source = None

        sep_date = None
        div_date = None
        
        married = 1
        engaged = 0

        # skip to marriage date in case person contained unmatches tokens
        #Alex: this failed when fields[idx] was an empty line. Fixed.
	#while idx < len(fields) and not fields[idx][0] == "+":
        while idx < len(fields) and not (fields[idx] and fields[idx][0] == "+"):
            print "Unknown field: "+fields[idx]
            idx = idx + 1

        while idx < len(fields) and mariageDataRe.match(fields[idx]):
            if fields[idx][0] == "+":
                mar_date = self.parse_date(self.decode(fields[idx]))
                print " Married at: %s" % fields[idx]
                idx = idx + 1
            elif fields[idx][0] == "-":
                div_date = self.parse_date(self.decode(fields[idx]))
                print " Div at: %s" % fields[idx]
                idx = idx + 1
            elif fields[idx] == "#mp":
                idx = idx + 1
                mar_place = self.get_or_create_place(self.decode(fields[idx]))
                print " Marriage place: %s" % fields[idx]
                idx = idx + 1
            elif fields[idx] == "#ms":
                idx = idx + 1
                mar_source = self.get_or_create_source(self.decode(fields[idx]))
                print " Marriage source: %s" % fields[idx]
                idx = idx + 1
            elif fields[idx] == "#sep":
                idx = idx + 1
                sep_date = self.parse_date(self.decode(fields[idx]))
                print " Seperated since: %s" % fields[idx]
                idx = idx + 1
            elif fields[idx] == "#np":
                print " Are not married."
                married = 0
                idx = idx + 1
            elif fields[idx] == "#eng":
                print " Are engaged."
                engaged = 1
                idx = idx + 1
            else:
                print "Unknown field for mariage: %s" % fields[idx]
                idx = idx + 1

        if mar_date or mar_place or mar_source:
            mar = self.create_event("Marriage", None, mar_date, mar_place, mar_source)
            self.current_family.add_event_handle(mar.get_handle())

        if div_date:
            div = self.create_event("Divorce", None, div_date, None, None)
            self.current_family.add_event_handle(div.get_handle())

        if sep_date or engaged:
            sep = self.create_event("Engagement", None, sep_date, None, None)
            self.current_family.add_event_handle(sep.get_handle())

        if not married:
            self.current_family.set_relationship(RelLib.Family.UNMARRIED)
            
        self.db.commit_family(self.current_family,self.trans)
        return idx

    def parse_person(self,fields,idx,gender,father_surname):
        firstname = ""
        surname = ""
        occupation = ""
        birthplace = ""
        alias = ""
        
        if not father_surname:
            if not idx < len(fields):
                print "Missing surname of person"
                return (idx,None)
            surname = self.decode(fields[idx])
            idx = idx + 1
        else:
            surname = father_surname
        
        if not idx < len(fields):
            print "Missing firstname of person"
            return (idx,None)
        firstname = self.decode(self.cnv(fields[idx]))
        idx = idx + 1
        if idx < len(fields) and father_surname:
            noSurnameRe = re.compile("^[({\[~><?0-9#].*$")
            if not noSurnameRe.match(self.cnv(fields[idx])):
                surname = self.decode(fields[idx])
                idx = idx + 1

        print "Person: %s %s" % (firstname, surname)
        person = self.get_or_create_person(firstname,surname)
        name = RelLib.Name()
        name.set_type("Birth Name")
        name.set_first_name(firstname)
        name.set_surname(surname)
        person.set_primary_name(name)
        if gender != None:
            person.set_gender(gender)
        self.db.commit_person(person,self.trans)
        personDataRe = re.compile("^[0-9<>~#\[({!].*$")
        dateRe = re.compile("^[0-9~<>?]+.*$")
        
        source = None
        birth_date = None
        birth_place = None
        birth_source = None

        bapt_date = None
        bapt_place = None
        bapt_source = None

        death_date = None
        death_place = None
        death_source = None

        crem_date = None
        bur_date = None
        bur_place = None
        bur_source = None
        
        public_name = None
        firstname_aliases = []
        nick_names = []
        name_aliases = []
        surname_aliases = []
        
        while idx < len(fields) and personDataRe.match(fields[idx]):
            if fields[idx][0] == '(':
                print "Public Name: %s" % fields[idx]
                public_name = self.decode(fields[idx])
                idx = idx + 1
            elif fields[idx][0] == '{':
                print "Firstsname Alias: %s" % fields[idx]
                firstname_aliases.append(self.decode(fields[idx]))
                idx = idx + 1
            elif fields[idx][0] == '[':
                print "Titles: %s" % fields[idx]
                idx = idx + 1
            elif fields[idx] == '#nick':
                idx = idx + 1
                print "Nick Name: %s" % fields[idx]
                nick_names.append(self.decode(fields[idx]))
                idx = idx + 1
            elif fields[idx] == '#occu':
                idx = idx + 1
                print "Occupation: %s" % fields[idx]
                occu = self.create_event("Occupation",self.decode(fields[idx]))
                person.add_event_handle(occu.get_handle())
                self.db.commit_person(person,self.trans)
                idx = idx + 1
            elif fields[idx] == '#alias':
                idx = idx + 1
                print "Name Alias: %s" % fields[idx]
                name_aliases.append(self.decode(fields[idx]))
                idx = idx + 1
            elif fields[idx] == '#salias':
                idx = idx + 1
                print "Surname Alias: %s" % fields[idx]
                surname_aliases.append(self.decode(fields[idx]))
                idx = idx + 1
            elif fields[idx] == '#image':
                idx = idx + 1
                print "Image: %s" % fields[idx]
                idx = idx + 1
            elif fields[idx] == '#src':
                idx = idx + 1
                print "Source: %s" % fields[idx]
                source = self.get_or_create_source(self.decode(fields[idx]))
                idx = idx + 1
            elif fields[idx] == '#bs':
                idx = idx + 1
                print "Birth Source: %s" % fields[idx]
                birth_source = self.get_or_create_source(self.decode(fields[idx]))
                idx = idx + 1
            elif fields[idx][0] == '!':
                print "Baptize at: %s" % fields[idx]
                bapt_date = self.parse_date(self.decode(fields[idx]))
                idx = idx + 1
            elif fields[idx] == '#bp':
                idx = idx + 1
                print "Birth Place: %s" % fields[idx]
                birth_place = self.get_or_create_place(self.decode(fields[idx]))
                idx = idx + 1
            elif fields[idx] == '#pp':
                idx = idx + 1
                print "Baptize Place: %s" % fields[idx]
                bapt_place = self.get_or_create_place(self.decode(fields[idx]))
                idx = idx + 1
            elif fields[idx] == '#ps':
                idx = idx + 1
                print "Baptize Source: %s" % fields[idx]
                bapt_source = self.get_or_create_source(self.decode(fields[idx]))
                idx = idx + 1
            elif fields[idx] == '#dp':
                idx = idx + 1
                print "Death Place: %s" % fields[idx]
                death_place = self.get_or_create_place(self.decode(fields[idx]))
                idx = idx + 1
            elif fields[idx] == '#ds':
                idx = idx + 1
                print "Death Source: %s" % fields[idx]
                death_source = self.get_or_create_source(self.decode(fields[idx]))
                idx = idx + 1
            elif fields[idx] == '#buri':
                idx = idx + 1
                print "Burial Date: %s" % fields[idx]
                bur_date = self.parse_date(self.decode(fields[idx]))
                idx = idx + 1
            elif fields[idx] == '#crem':
                idx = idx + 1
                print "Cremention Date: %s" % fields[idx]
                crem_date = self.parse_date(self.decode(fields[idx]))
                idx = idx + 1
            elif fields[idx] == '#bp':
                idx = idx + 1
                print "Burial Place: %s" % fields[idx]
                bur_place = self.get_or_create_place(self.decode(fields[idx]))
                idx = idx + 1
            elif fields[idx] == '#rs':
                idx = idx + 1
                print "Burial Source: %s" % fields[idx]
                bur_source = self.get_or_create_source(self.decode(fields[idx]))
                idx = idx + 1
            elif fields[idx] == '#apubl':
                print "This is a public record"
                idx = idx + 1
            elif fields[idx] == '#apriv':
                print "This is a private record"
                idx = idx + 1
            elif dateRe.match( fields[idx]):
                if not birth_date:
                    print "Birth Date: %s" % fields[idx]
                    birth_date = self.parse_date(self.decode(fields[idx]))
                else:
                    print "Death Date: %s" % fields[idx]
                    death_date = self.parse_date(self.decode(fields[idx]))
                idx = idx + 1
            else:
                print "Unknown field for person: %s" % fields[idx]
                idx = idx + 1
        
        if public_name:
            name = person.get_primary_name()
            name.set_type("Birth Name")
            person.add_alternate_name(name)
            name = RelLib.Name()
            name.set_type("Also Known As")
            name.set_first_name(public_name)
            name.set_surname(surname)
            person.set_primary_name(name)
        
        i = 0
        for aka in nick_names:
            if i == 0:
                person.set_nick_name(aka)
            else:
                name = RelLib.Name()
                name.set_type("Also Known As")
                name.set_first_name(aka)
                name.set_surname(surname)
                person.add_alternate_name(name)
            i = i + 1        

        for aka in firstname_aliases:
            name = RelLib.Name()
            name.set_type("Also Known As")
            name.set_first_name(aka)
            name.set_surname(surname)
            person.add_alternate_name(name)

        for aka in name_aliases:
            name = RelLib.Name()
            name.set_type("Also Known As")
            name.set_first_name(aka)
            name.set_surname(surname)
            person.add_alternate_name(name)

        for aka in surname_aliases:
            name = RelLib.Name()
            name.set_type("Also Known As")
            if public_name:
                name.set_first_name(public_name)
            else:
                name.set_first_name(firstname)
            name.set_surname(aka)
            person.add_alternate_name(name)

        if source:
            person.add_source_reference(source)

        if birth_date or birth_place or birth_source:
            birth = self.create_event("Birth", None, birth_date, birth_place, birth_source)
            person.set_birth_handle(birth.get_handle())

        if bapt_date or bapt_place or bapt_source:
            babt = self.create_event("Baptism", None, bapt_date, bapt_place, bapt_source)
            person.add_event_handle(babt.get_handle())

        if death_date or death_place or death_source:
            babt = self.create_event("Death", None, death_date, death_place, death_source)
            person.set_death_handle(babt.get_handle())

        if bur_date:
            babt = self.create_event("Burial", None, bur_date, bur_place, bur_source)
            person.add_event_handle(babt.get_handle())

        if crem_date:
            babt = self.create_event("Cremation", None, crem_date, bur_place, bur_source)
            person.add_event_handle(babt.get_handle())

        self.db.commit_person(person,self.trans)

        return (idx,person)
        
    def parse_date(self,field):
        #Alex: this should do the trick
        date = self.dp.parse(field)
        return date
        
    def create_event(self,type,desc=None,date=None,place=None,source=None):
        event = RelLib.Event()
        if type:
            event.set_name(type)
        if desc:
            event.set_description(desc)
        if date:
            event.set_date_object(date)
        if place:
            event.set_place_handle(place.get_handle())
        if source:
            event.add_source_reference(source)
        self.db.add_event(event,self.trans)
        self.db.commit_event(event,self.trans)
        return event
    
    def get_or_create_person(self,firstname,lastname):
        person = None
        mykey = firstname+lastname
        if mykey in self.ikeys:
            person = self.db.get_person_from_handle(self.ikeys[mykey])
        else:
            person = RelLib.Person()
            self.db.add_person(person,self.trans)
            self.db.commit_person(person,self.trans)
            self.ikeys[mykey] = person.get_handle()
        return person

    def get_or_create_place(self,place_name):
        place = None
        if place_name in self.pkeys:
            person = self.db.get_place_from_handle(self.pkeys[place_name])
        else:
            place = RelLib.Place()
            place.set_title(place_name)
            self.db.add_place(place,self.trans)
            self.db.commit_place(place,self.trans)
            self.pkeys[place_name] = place.get_handle()
        return place

    def get_or_create_source(self,source_name):
        source = None
        if source_name in self.skeys:
            source = self.db.get_source_from_handle(self.skeys[source_name])
        else:
            source = RelLib.Source()
            source.set_title(source_name)
            self.db.add_source(source,self.trans)
            self.db.commit_source(source,self.trans)
            self.skeys[source_name] = source.get_handle()
        sref = RelLib.SourceRef()
        sref.set_base_handle(source.get_handle())
        return sref

    def decode(self,s):
        return( latin_utf8.latin_to_utf8( s.replace('_',' ')))

    def cnv(seld,s):
        return( latin_utf8.latin_to_utf8(s))

#-------------------------------------------------------------------------
#
#
#
#-------------------------------------------------------------------------
_mime_type = 'application/x-geneweb'
_filter = gtk.FileFilter()
_filter.set_name(_('GeneWeb files'))
_filter.add_mime_type(_mime_type)

from Plugins import register_import
register_import(importData,_filter,_mime_type,1)

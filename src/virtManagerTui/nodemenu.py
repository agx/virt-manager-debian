# mainmenu.py - Copyright (C) 2009 Red Hat, Inc.
# Written by Darryl L. Pierce <dpierce@redhat.com>
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; version 2 of the License.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston,
# MA  02110-1301, USA.  A copy of the GNU General Public License is
# also available at http://www.gnu.org/copyleft/gpl.html.

from snack import *
import traceback

from menuscreen     import MenuScreen
from configscreen   import ConfigScreen
from adddomain      import AddDomain
from startdomain    import StartDomain
from stopdomain     import StopDomain
from removedomain   import RemoveDomain
from listdomains    import ListDomains
from migratedomain  import MigrateDomain
from createuser     import CreateUser

import utils
import logging

ADD_DOMAIN     = 1
START_DOMAIN   = 2
STOP_DOMAIN    = 3
REMOVE_DOMAIN  = 4
LIST_DOMAINS   = 5
MIGRATE_DOMAIN = 6
CREATE_USER    = 7

class NodeMenuScreen(MenuScreen):
    def __init__(self):
        MenuScreen.__init__(self, "Node Administration")

    def get_menu_items(self):
        return (("Add A Virtual Machine",     ADD_DOMAIN),
                ("Start A Virtual Machine",  START_DOMAIN),
                ("Stop A Virtual Machine",    STOP_DOMAIN),
                ("Remove A Virtual Machine",  REMOVE_DOMAIN),
                ("List All Virtual Machines", LIST_DOMAINS),
                ("Migrate Virtual Machine",   MIGRATE_DOMAIN),
                ("Create A User",             CREATE_USER))

    def handle_selection(self, item):
            if   item is ADD_DOMAIN:     AddDomain()
            elif item is START_DOMAIN:   StartDomain()
            elif item is STOP_DOMAIN:    StopDomain()
            elif item is REMOVE_DOMAIN:  RemoveDomain()
            elif item is LIST_DOMAINS:   ListDomains()
            elif item is MIGRATE_DOMAIN: MigrateDomain()
            elif item is CREATE_USER:    CreateUser()

def NodeMenu():
    screen = NodeMenuScreen()
    screen.start()

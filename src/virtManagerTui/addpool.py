# addstorage.py - Copyright (C) 2009 Red Hat, Inc.
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
import utils

from configscreen import *
from poolconfig import PoolConfig
from virtinst import Storage

POOL_NAME_PAGE    = 1
POOL_DETAILS_PAGE = 2
CONFIRM_PAGE      = 3

class AddStoragePoolConfigScreen(ConfigScreen):
    def __init__(self):
        ConfigScreen.__init__(self, "Add A Storage Pool")
        self.__config = PoolConfig(self.get_libvirt())

    def get_elements_for_page(self, screen, page):
        if   page is POOL_NAME_PAGE:    return self.get_pool_name_page(screen)
        elif page is POOL_DETAILS_PAGE: return self.get_pool_details_page(screen)
        elif page is CONFIRM_PAGE:      return self.get_confirm_page(screen)

    def page_has_next(self, page):
        return page < CONFIRM_PAGE

    def page_has_back(self, page):
        return page > POOL_NAME_PAGE

        return page > POOL_NAME_PAGE

    def page_has_finish(self, page):
        return page is CONFIRM_PAGE

    def validate_input(self, page, errors):
        if   page is POOL_NAME_PAGE:
            if utils.string_is_not_blank(self.__name.value()):
                if self.get_libvirt().storage_pool_exists(self.__name.value()):
                    errors.append("Name '%s' already in use by another pool." % self.__name.value())
                else:
                    return True
            else:
                errors.append("Storage object name must be a string between 0 and 50 characters.")
        elif page is POOL_DETAILS_PAGE:
            result = True
            if self.__config.needs_target_path():
                if utils.string_is_not_blank(self.__target_path.value()):
                    if self.__target_path.value()[0:1] is not '/':
                        errors.append("'%s' is not an absolute path." % self.__target_path.value())
                        result = False
                else:
                    errors.append("You must enter a target path.")
                    result = False
            if self.__config.needs_format():
                if self.__formats.getSelection() is None:
                    errors.append("You must select a pool format.")
                    result = False
            if self.__config.needs_hostname():
                if not utils.string_is_not_blank(self.__hostname.value()):
                    errors.append("You must enter a hostname.")
                    result = False
            if self.__config.needs_source_path():
                if utils.string_is_not_blank(self.__source_path.value()):
                    if self.__config.source_must_be_absolute():
                        if self.__source_path.value()[0:1] is not '/':
                            errors.append("'%s' is not an absolute path." % self.__source_path.value())
                            result = False
                else:
                    errors.append("you  must enter a source path.")
                    result = False
            return result
        elif page is CONFIRM_PAGE: return True
        return False

    def process_input(self, page):
        if page is POOL_NAME_PAGE:
            self.__config.set_name(self.__name.value())
            self.__config.set_type(self.__type.getSelection())
            #self._reset_flags(self.__type.current())
        elif page is POOL_DETAILS_PAGE:
            if self.__config.needs_target_path():
                self.__config.set_target_path(self.__target_path.value())
            if self.__config.needs_format():
                self.__config.set_format(self.__formats.getSelection())
            if self.__config.needs_hostname():
                self.__config.set_hostname(self.__hostname.value())
            if self.__config.needs_source_path():
                self.__config.set_source_path(self.__source_path.value())
            if self.__config.needs_build_pool():
                self.__config.set_build_pool(self.__build_pool.value())
        elif page is CONFIRM_PAGE:
            self.get_libvirt().define_storage_pool(self.__config.get_name(), config = self.__config)
            self.get_libvirt().create_storage_pool(self.__config.get_name())
            self.set_finished()

    def get_pool_name_page(self, screen):
        self.__name = Entry(50, self.__config.get_name())
        pooltypes = []
        for pooltype in Storage.StoragePool.get_pool_types():
            pooltypes.append(["%s: %s" % (pooltype, Storage.StoragePool.get_pool_type_desc(pooltype)),
                              pooltype,
                              self.__config.get_type() is pooltype])
        self.__type = RadioBar(screen, pooltypes)
        grid = Grid(2, 2)
        grid.setField(Label("Name:"), 0, 0, anchorRight = 1)
        grid.setField(self.__name, 1, 0, anchorLeft = 1)
        grid.setField(Label("Type:"), 0, 1, anchorRight = 1, anchorTop = 1)
        grid.setField(self.__type, 1, 1, anchorLeft = 1)
        return [Label("Add Storage Pool"),
                grid]

    def get_pool_details_page(self, screen):
        rows = 0
        if self.__config.needs_target_path():
            self.__target_path = Entry(50, self.__config.get_target_path())
            rows += 1
        if self.__config.needs_format():
            formats = []
            for format in self.__config.get_formats():
                formats.append([format, format, format is self.__config.get_format()])
            self.__formats = RadioBar(screen, formats)
            rows += 1
        if self.__config.needs_hostname():
            self.__hostname = Entry(50, self.__config.get_hostname())
            rows += 1
        if self.__config.needs_source_path():
            self.__source_path = Entry(50, self.__config.get_source_path())
            rows += 1
        if self.__config.needs_build_pool():
            self.__build_pool = Checkbox("Build Pool", self.__config.get_build_pool())
            rows += 1
            self.__build_pool = Checkbox("Build Pool", self.__config.get_build_pool())
            rows += 1
        grid = Grid(2, rows)
        currentrow = 0
        if self.__config.needs_target_path():
            grid.setField(Label("Target Path:"), 0, currentrow, anchorRight = 1)
            grid.setField(self.__target_path, 1, currentrow, anchorLeft = 1)
            currentrow += 1
        if self.__config.needs_format():
            grid.setField(Label("Format:"), 0, currentrow, anchorRight = 1, anchorTop = 1)
            grid.setField(self.__formats, 1, currentrow, anchorLeft = 1)
            currentrow += 1
        if self.__config.needs_hostname():
            grid.setField(Label("Host Name:"), 0, currentrow, anchorRight = 1)
            grid.setField(self.__hostname, 1, currentrow, anchorRight = 1)
            currentrow += 1
        if self.__config.needs_source_path():
            grid.setField(Label("Source Path:"), 0, currentrow, anchorRight = 1)
            grid.setField(self.__source_path, 1, currentrow, anchorLeft = 1)
            currentrow += 1
        if self.__config.needs_build_pool():
            grid.setField(Label(" "), 0, currentrow, anchorRight = 1)
            grid.setField(self.__build_pool, 1, currentrow, anchorLeft = 1)
            currentrow += 1
        return [Label("Specify a storage location to be later split into virtual machine storage"),
                grid]

    def get_confirm_page(self, screen):
        grid = Grid(2, 2)
        grid.setField(Label("Name:"), 0, 0, anchorRight = 1)
        grid.setField(Label(self.__config.get_name()), 1, 0, anchorLeft = 1)
        grid.setField(Label("Target Path:"), 0, 1, anchorRight = 1)
        grid.setField(Label(self.__config.get_target_path()), 1, 1, anchorLeft = 1)
        return [Label("Confirm Pool Details"),
                grid]

def AddStoragePool():
    screen = AddStoragePoolConfigScreen()
    screen.start()

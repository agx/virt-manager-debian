#
# Copyright (C) 2009 Red Hat, Inc.
# Copyright (C) 2009 Cole Robinson <crobinso@redhat.com>
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
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston,
# MA 02110-1301 USA.
#

import logging

# pylint: disable=E0611
from gi.repository import GObject
from gi.repository import Gtk
# pylint: enable=E0611

from virtManager.baseclass import vmmGObject
from virtManager.error import vmmErrorDialog

try:
    from gi.repository import AppIndicator3  # pylint: disable=E0611
except:
    AppIndicator3 = None


def build_image_menu_item(label):
    hasfunc = hasattr(Gtk.ImageMenuItem, "set_use_underline")
    if hasfunc:
        label.replace("_", "__")

    menu_item = Gtk.ImageMenuItem(label)
    if hasfunc:
        menu_item.set_use_underline(False)

    return menu_item


class vmmSystray(vmmGObject):
    __gsignals__ = {
        "action-toggle-manager": (GObject.SignalFlags.RUN_FIRST, None, []),
        "action-view-manager": (GObject.SignalFlags.RUN_FIRST, None, []),
        "action-suspend-domain": (GObject.SignalFlags.RUN_FIRST, None, [str, str]),
        "action-resume-domain": (GObject.SignalFlags.RUN_FIRST, None, [str, str]),
        "action-run-domain": (GObject.SignalFlags.RUN_FIRST, None, [str, str]),
        "action-shutdown-domain": (GObject.SignalFlags.RUN_FIRST, None, [str, str]),
        "action-reset-domain": (GObject.SignalFlags.RUN_FIRST, None, [str, str]),
        "action-reboot-domain": (GObject.SignalFlags.RUN_FIRST, None, [str, str]),
        "action-destroy-domain": (GObject.SignalFlags.RUN_FIRST, None, [str, str]),
        "action-show-host": (GObject.SignalFlags.RUN_FIRST, None, [str]),
        "action-show-vm": (GObject.SignalFlags.RUN_FIRST, None, [str, str]),
        "action-exit-app": (GObject.SignalFlags.RUN_FIRST, None, []),
    }

    def __init__(self, engine):
        vmmGObject.__init__(self)

        self.topwin = None
        self.err = vmmErrorDialog()

        self.conn_menuitems = {}
        self.conn_vm_menuitems = {}
        self.vm_action_dict = {}
        self.systray_menu = None
        self.systray_icon = None
        self.systray_indicator = False

        engine.connect("conn-added", self.conn_added)
        engine.connect("conn-removed", self.conn_removed)

        # Are we using Application Indicators?
        if AppIndicator3 is not None:
            self.systray_indicator = True

        self.init_systray_menu()

        self.add_gconf_handle(
            self.config.on_view_system_tray_changed(self.show_systray))

        self.show_systray()

    def is_visible(self):
        if self.systray_indicator:
            return (self.config.get_view_system_tray() and
                    self.systray_icon)
        else:
            return (self.config.get_view_system_tray() and
                    self.systray_icon and
                    self.systray_icon.is_embedded())

    def _cleanup(self):
        self.err = None

        if self.systray_menu:
            self.systray_menu.destroy()
            self.systray_menu = None

        self.systray_icon = None

    # Initialization routines

    def init_systray_menu(self):
        """
        Do we want notifications?

        Close App
        Hide app? As in, only have systray active? is that possible?
            Have one of those 'minimize to tray' notifications?

        """
        self.systray_menu = Gtk.Menu()

        self.systray_menu.add(Gtk.SeparatorMenuItem())

        if self.systray_indicator:
            hide_item = Gtk.MenuItem("_Show Virtual Machine Manager")
            hide_item.connect("activate", self.systray_activate)
            self.systray_menu.add(hide_item)

        exit_item = Gtk.ImageMenuItem.new_from_stock(Gtk.STOCK_QUIT, None)
        exit_item.connect("activate", self.exit_app)
        self.systray_menu.add(exit_item)
        self.systray_menu.show_all()

    def init_systray(self):
        # Build the systray icon
        if self.systray_icon:
            return

        if self.systray_indicator:
            self.systray_icon = AppIndicator3.Indicator("virt-manager",
                                "virt-manager-icon",
                                AppIndicator3.CATEGORY_OTHER)
            self.systray_icon.set_status(AppIndicator3.STATUS_ACTIVE)
            self.systray_icon.set_menu(self.systray_menu)

        else:
            self.systray_icon = Gtk.StatusIcon()
            self.systray_icon.set_visible(True)
            self.systray_icon.set_property("icon-name", "virt-manager")
            self.systray_icon.connect("activate", self.systray_activate)
            self.systray_icon.connect("popup-menu", self.systray_popup)
            self.systray_icon.set_tooltip_text(_("Virtual Machine Manager"))

    def show_systray(self):
        do_show = self.config.get_view_system_tray()
        logging.debug("Showing systray: %s", do_show)

        if not self.systray_icon:
            if do_show:
                self.init_systray()
        else:
            if self.systray_indicator:
                if do_show:
                    self.systray_icon.set_status(AppIndicator3.STATUS_ACTIVE)
                else:
                    self.systray_icon.set_status(AppIndicator3.STATUS_PASSIVE)
            else:
                self.systray_icon.set_visible(do_show)

    def build_vm_menu(self, vm):
        icon_size = Gtk.IconSize.MENU

        pause_item = Gtk.ImageMenuItem.new_with_mnemonic(_("_Pause"))
        pause_img  = Gtk.Image.new_from_stock(Gtk.STOCK_MEDIA_PAUSE, icon_size)
        pause_item.set_image(pause_img)
        pause_item.connect("activate", self.run_vm_action,
                           "action-suspend-domain", vm.get_uuid())

        resume_item = Gtk.ImageMenuItem.new_with_mnemonic(_("_Resume"))
        resume_img  = Gtk.Image.new_from_stock(Gtk.STOCK_MEDIA_PAUSE,
                                               icon_size)
        resume_item.set_image(resume_img)
        resume_item.connect("activate", self.run_vm_action,
                            "action-resume-domain", vm.get_uuid())

        run_item = Gtk.ImageMenuItem.new_with_mnemonic(_("_Run"))
        run_img  = Gtk.Image.new_from_stock(Gtk.STOCK_MEDIA_PLAY, icon_size)
        run_item.set_image(run_img)
        run_item.connect("activate", self.run_vm_action,
                         "action-run-domain", vm.get_uuid())

        # Shutdown menu
        reboot_item = Gtk.ImageMenuItem.new_with_mnemonic(_("_Reboot"))
        reboot_img = Gtk.Image.new_from_icon_name("system-shutdown", icon_size)
        reboot_item.set_image(reboot_img)
        reboot_item.connect("activate", self.run_vm_action,
                            "action-reboot-domain", vm.get_uuid())
        reboot_item.show()

        shutdown_item = Gtk.ImageMenuItem.new_with_mnemonic(_("_Shut Down"))
        shutdown_img = Gtk.Image.new_from_icon_name("system-shutdown",
                                                    icon_size)
        shutdown_item.set_image(shutdown_img)
        shutdown_item.connect("activate", self.run_vm_action,
                              "action-shutdown-domain", vm.get_uuid())
        shutdown_item.show()

        reset_item = Gtk.ImageMenuItem.new_with_mnemonic(_("_Force Reset"))
        reset_img = Gtk.Image.new_from_icon_name("system-shutdown", icon_size)
        reset_item.set_image(reset_img)
        reset_item.show()
        reset_item.connect("activate", self.run_vm_action,
                           "action-reset-domain", vm.get_uuid())

        destroy_item = Gtk.ImageMenuItem.new_with_mnemonic(_("_Force Off"))
        destroy_img = Gtk.Image.new_from_icon_name("system-shutdown",
                                                   icon_size)
        destroy_item.set_image(destroy_img)
        destroy_item.show()
        destroy_item.connect("activate", self.run_vm_action,
                             "action-destroy-domain", vm.get_uuid())

        shutdown_menu = Gtk.Menu()
        shutdown_menu.add(reboot_item)
        shutdown_menu.add(shutdown_item)
        shutdown_menu.add(reset_item)
        shutdown_menu.add(destroy_item)
        shutdown_menu_item = Gtk.ImageMenuItem.new_with_mnemonic(_("_Shut Down"))
        shutdown_menu_img = Gtk.Image.new_from_icon_name("system-shutdown",
                                                         icon_size)
        shutdown_menu_item.set_image(shutdown_menu_img)
        shutdown_menu_item.set_submenu(shutdown_menu)

        sep = Gtk.SeparatorMenuItem()

        open_item = Gtk.ImageMenuItem.new_from_stock("gtk-open", None)
        open_item.show()
        open_item.connect("activate", self.run_vm_action,
                          "action-show-vm", vm.get_uuid())

        vm_action_dict = {}
        vm_action_dict["run"] = run_item
        vm_action_dict["pause"] = pause_item
        vm_action_dict["resume"] = resume_item
        vm_action_dict["shutdown_menu"] = shutdown_menu_item
        vm_action_dict["reboot"] = reboot_item
        vm_action_dict["shutdown"] = shutdown_item
        vm_action_dict["reset"] = reset_item
        vm_action_dict["destroy"] = destroy_item
        vm_action_dict["sep"] = sep
        vm_action_dict["open"] = open_item

        menu = Gtk.Menu()

        for key in ["run", "pause", "resume", "shutdown_menu", "sep", "open"]:
            item = vm_action_dict[key]
            item.show_all()
            menu.add(vm_action_dict[key])

        return menu, vm_action_dict

    # Helper functions
    def _get_vm_menu_item(self, vm):
        uuid = vm.get_uuid()
        uri = vm.conn.get_uri()

        if uri in self.conn_vm_menuitems:
            if uuid in self.conn_vm_menuitems[uri]:
                return self.conn_vm_menuitems[uri][uuid]
        return None

    def _set_vm_status_icon(self, vm, menu_item):
        image = Gtk.Image()
        image.set_from_icon_name(vm.run_status_icon_name(),
                                 Gtk.IconSize.MENU)
        image.set_sensitive(vm.is_active())
        menu_item.set_image(image)

    # Listeners

    def systray_activate(self, widget_ignore):
        self.emit("action-toggle-manager")

    def systray_popup(self, widget_ignore, button, event_time):
        if button != 3:
            return

        self.systray_menu.popup(None, None, Gtk.StatusIcon.position_menu,
                                self.systray_icon, 0, event_time)

    def repopulate_menu_list(self):
        # Build sorted connection list
        connsort = self.conn_menuitems.keys()
        connsort.sort()
        connsort.reverse()

        # Empty conn list
        for child in self.systray_menu.get_children():
            if child in self.conn_menuitems.values():
                self.systray_menu.remove(child)

        # Build sorted conn list
        for uri in connsort:
            self.systray_menu.insert(self.conn_menuitems[uri], 0)


    def conn_added(self, engine_ignore, conn):
        conn.connect("vm-added", self.vm_added)
        conn.connect("vm-removed", self.vm_removed)
        conn.connect("state-changed", self.conn_state_changed)

        if conn.get_uri() in self.conn_menuitems:
            return

        menu_item = Gtk.MenuItem.new_with_label(conn.get_pretty_desc_inactive())
        menu_item.show()
        vm_submenu = Gtk.Menu()
        vm_submenu.show()
        menu_item.set_submenu(vm_submenu)

        self.conn_menuitems[conn.get_uri()] = menu_item
        self.conn_vm_menuitems[conn.get_uri()] = {}

        self.repopulate_menu_list()

        self.conn_state_changed(conn)
        self.populate_vm_list(conn)

    def conn_removed(self, engine_ignore, uri):
        if not uri in self.conn_menuitems:
            return

        menu_item = self.conn_menuitems[uri]
        self.systray_menu.remove(menu_item)
        menu_item.destroy()
        del(self.conn_menuitems[uri])
        self.conn_vm_menuitems[uri] = {}

        self.repopulate_menu_list()

    def conn_state_changed(self, conn):
        sensitive = conn.is_active()
        menu_item = self.conn_menuitems[conn.get_uri()]
        menu_item.set_sensitive(sensitive)

    def populate_vm_list(self, conn):
        uri = conn.get_uri()
        conn_menu_item = self.conn_menuitems[uri]
        vm_submenu = conn_menu_item.get_submenu()

        # Empty conn menu
        for c in vm_submenu.get_children():
            vm_submenu.remove(c)

        vm_mappings = {}
        for vm in conn.vms.values():
            vm_mappings[vm.get_name()] = vm.get_uuid()

        vm_names = vm_mappings.keys()
        vm_names.sort()

        if len(vm_names) == 0:
            menu_item = Gtk.MenuItem(_("No virtual machines"))
            menu_item.set_sensitive(False)
            vm_submenu.insert(menu_item, 0)
            return

        for i in range(0, len(vm_names)):
            name = vm_names[i]
            uuid = vm_mappings[name]
            if uuid in self.conn_vm_menuitems[uri]:
                vm_item = self.conn_vm_menuitems[uri][uuid]
                vm_submenu.insert(vm_item, i)

    def vm_added(self, conn, uuid):
        uri = conn.get_uri()
        vm = conn.get_vm(uuid)
        if not vm:
            return
        vm.connect("status-changed", self.vm_state_changed)

        vm_mappings = self.conn_vm_menuitems[uri]
        if uuid in vm_mappings:
            return

        # Build VM list entry
        menu_item = build_image_menu_item(vm.get_name())
        vm_mappings[uuid] = menu_item
        vm_action_menu, vm_action_dict = self.build_vm_menu(vm)
        menu_item.set_submenu(vm_action_menu)
        self.vm_action_dict[uuid] = vm_action_dict

        # Add VM to menu list
        self.populate_vm_list(conn)

        # Update state
        self.vm_state_changed(vm)
        menu_item.show()

    def vm_removed(self, conn, uuid):
        uri = conn.get_uri()
        vm_mappings = self.conn_vm_menuitems[uri]
        if not vm_mappings:
            return

        if uuid in vm_mappings:
            conn_item = self.conn_menuitems[uri]
            vm_menu_item = vm_mappings[uuid]
            vm_menu = conn_item.get_submenu()
            vm_menu.remove(vm_menu_item)
            vm_menu_item.destroy()
            del(vm_mappings[uuid])

            if len(vm_menu.get_children()) == 0:
                placeholder = Gtk.MenuItem(_("No virtual machines"))
                placeholder.show()
                placeholder.set_sensitive(False)
                vm_menu.add(placeholder)

    def vm_state_changed(self, vm, ignore=None, ignore2=None):
        menu_item = self._get_vm_menu_item(vm)
        if not menu_item:
            return

        self._set_vm_status_icon(vm, menu_item)

        # Update action widget states
        actions = self.vm_action_dict[vm.get_uuid()]

        is_paused = vm.is_paused()
        actions["run"].set_sensitive(vm.is_runable())
        actions["pause"].set_sensitive(vm.is_pauseable())
        actions["resume"].set_sensitive(vm.is_paused())
        actions["shutdown_menu"].set_sensitive(vm.is_active())
        actions["shutdown"].set_sensitive(vm.is_stoppable())
        actions["reboot"].set_sensitive(vm.is_stoppable())
        actions["reset"].set_sensitive(vm.is_destroyable())
        actions["destroy"].set_sensitive(vm.is_destroyable())

        actions["pause"].set_property("visible", not is_paused)
        actions["resume"].set_property("visible", is_paused)

    def run_vm_action(self, ignore, signal_name, uuid):
        uri = None
        for tmpuri, vm_mappings in self.conn_vm_menuitems.items():
            if vm_mappings.get(uuid):
                uri = tmpuri
                break

        if not uri:
            return

        self.emit(signal_name, uri, uuid)

    def exit_app(self, ignore):
        self.emit("action-exit-app")

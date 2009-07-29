#
# Copyright (C) 2006-2008 Red Hat, Inc.
# Copyright (C) 2006 Daniel P. Berrange <berrange@redhat.com>
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

import gobject
import gtk
import gtk.glade
import logging
import traceback

import libvirt

import virtManager.config as cfg
from virtManager.connection import vmmConnection
from virtManager.asyncjob import vmmAsyncJob
from virtManager.error import vmmErrorDialog
from virtManager.delete import vmmDeleteDialog
from virtManager.graphwidgets import CellRendererSparkline
from virtManager import util as util

VMLIST_SORT_NAME = 1
VMLIST_SORT_STATS = 2

# fields in the tree model data set
ROW_HANDLE = 0
ROW_NAME = 1
ROW_MARKUP = 2
ROW_STATUS = 3
ROW_STATUS_ICON = 4
ROW_KEY = 5
ROW_HINT = 6
ROW_IS_CONN = 7
ROW_IS_CONN_CONNECTED = 8
ROW_IS_VM = 9
ROW_IS_VM_RUNNING = 10
ROW_COLOR = 11
ROW_HEIGHT = 12

# Columns in the tree view
COL_NAME = 0
COL_STATUS = 1
COL_STATS = 2

rcstring = """
style "toolbar-style" {
    #GtkToolbar::button_relief = GTK_RELIEF_NONE
    #GtkToolbar::shadow_type = GTK_SHADOW_NONE
    GtkToolbar::internal_padding = 2
}
style "treeview-style" {
    GtkTreeView::indent_expanders = 0
}

class "GtkToolbar" style "toolbar-style"
class "GtkTreeView" style "treeview-style"
"""
gtk.rc_parse_string(rcstring)

def build_shutdown_button_menu(config, widget, shutdown_cb, reboot_cb,
                               destroy_cb):
    icon_name = config.get_shutdown_icon_name()
    widget.set_icon_name(icon_name)
    menu = gtk.Menu()
    widget.set_menu(menu)

    rebootimg = gtk.image_new_from_icon_name(icon_name, gtk.ICON_SIZE_MENU)
    shutdownimg = gtk.image_new_from_icon_name(icon_name, gtk.ICON_SIZE_MENU)
    destroyimg = gtk.image_new_from_icon_name(icon_name, gtk.ICON_SIZE_MENU)

    reboot = gtk.ImageMenuItem(_("_Reboot"))
    reboot.set_image(rebootimg)
    reboot.show()
    reboot.connect("activate", reboot_cb)
    menu.add(reboot)

    shutdown = gtk.ImageMenuItem(_("_Shut Down"))
    shutdown.set_image(shutdownimg)
    shutdown.show()
    shutdown.connect("activate", shutdown_cb)
    menu.add(shutdown)

    destroy = gtk.ImageMenuItem(_("_Force Off"))
    destroy.set_image(destroyimg)
    destroy.show()
    destroy.connect("activate", destroy_cb)
    menu.add(destroy)


class vmmManager(gobject.GObject):
    __gsignals__ = {
        "action-show-connect":(gobject.SIGNAL_RUN_FIRST,
                                  gobject.TYPE_NONE, []),
        "action-show-console": (gobject.SIGNAL_RUN_FIRST,
                                gobject.TYPE_NONE, (str,str)),
        "action-show-terminal": (gobject.SIGNAL_RUN_FIRST,
                                gobject.TYPE_NONE, (str,str)),
        "action-refresh-console": (gobject.SIGNAL_RUN_FIRST,
                                   gobject.TYPE_NONE, (str,str)),
        "action-refresh-terminal": (gobject.SIGNAL_RUN_FIRST,
                                    gobject.TYPE_NONE, (str,str)),
        "action-show-details": (gobject.SIGNAL_RUN_FIRST,
                                gobject.TYPE_NONE, (str,str)),
        "action-show-about": (gobject.SIGNAL_RUN_FIRST,
                              gobject.TYPE_NONE, []),
        "action-show-host": (gobject.SIGNAL_RUN_FIRST,
                              gobject.TYPE_NONE, [str]),
        "action-show-preferences": (gobject.SIGNAL_RUN_FIRST,
                                    gobject.TYPE_NONE, []),
        "action-show-create": (gobject.SIGNAL_RUN_FIRST,
                               gobject.TYPE_NONE, [str]),
        "action-suspend-domain": (gobject.SIGNAL_RUN_FIRST,
                                  gobject.TYPE_NONE, (str, str)),
        "action-resume-domain": (gobject.SIGNAL_RUN_FIRST,
                                 gobject.TYPE_NONE, (str, str)),
        "action-run-domain": (gobject.SIGNAL_RUN_FIRST,
                              gobject.TYPE_NONE, (str, str)),
        "action-shutdown-domain": (gobject.SIGNAL_RUN_FIRST,
                                   gobject.TYPE_NONE, (str, str)),
        "action-reboot-domain": (gobject.SIGNAL_RUN_FIRST,
                                 gobject.TYPE_NONE, (str, str)),
        "action-destroy-domain": (gobject.SIGNAL_RUN_FIRST,
                                  gobject.TYPE_NONE, (str, str)),
        "action-connect": (gobject.SIGNAL_RUN_FIRST,
                           gobject.TYPE_NONE, [str]),
        "action-show-help": (gobject.SIGNAL_RUN_FIRST,
                               gobject.TYPE_NONE, [str]),
        "action-migrate-domain": (gobject.SIGNAL_RUN_FIRST,
                                  gobject.TYPE_NONE, (str,str,str)),
        "action-clone-domain": (gobject.SIGNAL_RUN_FIRST,
                                gobject.TYPE_NONE, (str,str)),
        "action-exit-app": (gobject.SIGNAL_RUN_FIRST,
                            gobject.TYPE_NONE, []),}

    def __init__(self, config, engine):
        self.__gobject_init__()
        self.window = gtk.glade.XML(config.get_glade_dir() + "/vmm-manager.glade", "vmm-manager", domain="virt-manager")
        self.err = vmmErrorDialog(self.window.get_widget("vmm-manager"),
                                  0, gtk.MESSAGE_ERROR, gtk.BUTTONS_CLOSE,
                                  _("Unexpected Error"),
                                  _("An unexpected error occurred"))
        self.config = config
        self.engine = engine

        self.delete_dialog = None
        self.startup_error = None
        self.ignore_pause = False

        self.stats_column = None
        self.stats_sparkline = None

        self.prepare_vmlist()

        self.config.on_vmlist_stats_type_changed(self.stats_toggled_config)

        # Register callbacks with the global stats enable/disable values
        # that disable the associated vmlist widgets if reporting is disabled
        self.config.on_stats_enable_disk_poll_changed(self.enable_polling,
                                                      cfg.STATS_DISK)
        self.config.on_stats_enable_net_poll_changed(self.enable_polling,
                                                     cfg.STATS_NETWORK)

        self.vmmenu_icons = {}
        self.vmmenu_icons["run"] = gtk.Image()
        self.vmmenu_icons["run"].set_from_stock(gtk.STOCK_MEDIA_PLAY,
                                                gtk.ICON_SIZE_MENU)
        self.vmmenu_icons["pause"] = gtk.Image()
        self.vmmenu_icons["pause"].set_from_stock(gtk.STOCK_MEDIA_PAUSE,
                                                  gtk.ICON_SIZE_MENU)
        self.vmmenu_icons["resume"] = gtk.Image()
        self.vmmenu_icons["resume"].set_from_stock(gtk.STOCK_MEDIA_PAUSE,
                                                   gtk.ICON_SIZE_MENU)

        def set_toolbar_image(widget, iconfile, l, w):
            filename = self.config.get_icon_dir() + "/%s" % iconfile
            pixbuf = gtk.gdk.pixbuf_new_from_file_at_size(filename, l, w)
            image = gtk.image_new_from_pixbuf(pixbuf)
            self.window.get_widget(widget).set_icon_widget(image)

        set_toolbar_image("vm-new", "vm_new_wizard.png", 28, 28)
        set_toolbar_image("vm-open", "icon_console.png", 24, 24)
        build_shutdown_button_menu(self.config,
                                   self.window.get_widget("vm-shutdown"),
                                   self.poweroff_vm,
                                   self.reboot_vm,
                                   self.destroy_vm)

        tool2 = self.window.get_widget("vm-toolbar2")
        tool2.set_property("icon-size", gtk.ICON_SIZE_LARGE_TOOLBAR)
        for c in tool2.get_children():
            c.set_homogeneous(False)

        icon_name = self.config.get_shutdown_icon_name()
        rebootimg = gtk.image_new_from_icon_name(icon_name,
                                                 gtk.ICON_SIZE_MENU)
        shutdownimg = gtk.image_new_from_icon_name(icon_name,
                                                   gtk.ICON_SIZE_MENU)
        destroyimg = gtk.image_new_from_icon_name(icon_name,
                                                  gtk.ICON_SIZE_MENU)
        self.vmmenu_icons["reboot"] = rebootimg
        self.vmmenu_icons["poweroff"] = shutdownimg
        self.vmmenu_icons["forcepoweroff"] = destroyimg

        self.vmmenu = gtk.Menu()
        self.vmmenushutdown = gtk.Menu()
        self.vmmenu_items = {}
        self.vmmenushutdown_items = {}
        self.vmmenumigrate = gtk.Menu()

        self.vmmenu_items["run"] = gtk.ImageMenuItem(_("_Run"))
        self.vmmenu_items["run"].set_image(self.vmmenu_icons["run"])
        self.vmmenu_items["run"].show()
        self.vmmenu_items["run"].connect("activate", self.start_vm)
        self.vmmenu.add(self.vmmenu_items["run"])

        self.vmmenu_items["pause"] = gtk.ImageMenuItem(_("_Pause"))
        self.vmmenu_items["pause"].set_image(self.vmmenu_icons["pause"])
        self.vmmenu_items["pause"].set_sensitive(False)
        self.vmmenu_items["pause"].show()
        self.vmmenu_items["pause"].connect("activate", self.pause_vm)
        self.vmmenu.add(self.vmmenu_items["pause"])

        self.vmmenu_items["resume"] = gtk.ImageMenuItem(_("_Resume"))
        self.vmmenu_items["resume"].set_image(self.vmmenu_icons["resume"])
        self.vmmenu_items["resume"].show()
        self.vmmenu_items["resume"].connect("activate", self.resume_vm)
        self.vmmenu.add(self.vmmenu_items["resume"])


        self.vmmenu_items["shutdown"] = gtk.MenuItem(_("_Shut Down"))
        self.vmmenu_items["shutdown"].set_submenu(self.vmmenushutdown)
        self.vmmenu_items["shutdown"].show()
        self.vmmenu.add(self.vmmenu_items["shutdown"])

        self.vmmenushutdown_items["reboot"] = gtk.ImageMenuItem(_("_Reboot"))
        self.vmmenushutdown_items["reboot"].set_image(self.vmmenu_icons["reboot"])
        self.vmmenushutdown_items["reboot"].show()
        self.vmmenushutdown_items["reboot"].connect("activate", self.reboot_vm)
        self.vmmenushutdown.add(self.vmmenushutdown_items["reboot"])

        self.vmmenushutdown_items["poweroff"] = gtk.ImageMenuItem(_("_Shut Down"))
        self.vmmenushutdown_items["poweroff"].set_image(self.vmmenu_icons["poweroff"])
        self.vmmenushutdown_items["poweroff"].show()
        self.vmmenushutdown_items["poweroff"].connect("activate", self.poweroff_vm)
        self.vmmenushutdown.add(self.vmmenushutdown_items["poweroff"])

        self.vmmenushutdown_items["forcepoweroff"] = gtk.ImageMenuItem(_("_Force Off"))
        self.vmmenushutdown_items["forcepoweroff"].set_image(self.vmmenu_icons["forcepoweroff"])
        self.vmmenushutdown_items["forcepoweroff"].show()
        self.vmmenushutdown_items["forcepoweroff"].connect("activate", self.destroy_vm)
        self.vmmenushutdown.add(self.vmmenushutdown_items["forcepoweroff"])

        self.vmmenu_items["hsep1"] = gtk.SeparatorMenuItem()
        self.vmmenu_items["hsep1"].show()
        self.vmmenu.add(self.vmmenu_items["hsep1"])

        self.vmmenu_items["migrate"] = gtk.ImageMenuItem(_("_Migrate"))
        self.vmmenu_items["migrate"].set_submenu(self.vmmenumigrate)
        self.vmmenu_items["migrate"].show()
        self.vmmenu_items["migrate"].connect("activate",
                                             self.populate_migrate_submenu)
        self.vmmenu.add(self.vmmenu_items["migrate"])

        self.vmmenu_items["clone"] = gtk.ImageMenuItem("_Clone")
        self.vmmenu_items["clone"].show()
        self.vmmenu_items["clone"].connect("activate", self.open_clone_window)
        self.vmmenu.add(self.vmmenu_items["clone"])

        self.vmmenu_items["hsep2"] = gtk.SeparatorMenuItem()
        self.vmmenu_items["hsep2"].show()
        self.vmmenu.add(self.vmmenu_items["hsep2"])

        self.vmmenu_items["open"] = gtk.ImageMenuItem(gtk.STOCK_OPEN)
        self.vmmenu_items["open"].connect("activate", self.open_vm_console)
        self.vmmenu_items["open"].show()
        self.vmmenu.add(self.vmmenu_items["open"])

        self.vmmenu.show()

        # Mapping of VM UUID -> tree model rows to
        # allow O(1) access instead of O(n)
        self.rows = {}

        self.connmenu = gtk.Menu()
        self.connmenu_items = {}

        self.connmenu_items["create"] = gtk.ImageMenuItem(gtk.STOCK_NEW)
        self.connmenu_items["create"].show()
        self.connmenu_items["create"].connect("activate", self.new_vm)
        self.connmenu.add(self.connmenu_items["create"])

        self.connmenu_items["connect"] = gtk.ImageMenuItem(gtk.STOCK_CONNECT)
        self.connmenu_items["connect"].show()
        self.connmenu_items["connect"].connect("activate", self.open_connection)
        self.connmenu.add(self.connmenu_items["connect"])

        self.connmenu_items["disconnect"] = gtk.ImageMenuItem(gtk.STOCK_DISCONNECT)
        self.connmenu_items["disconnect"].show()
        self.connmenu_items["disconnect"].connect("activate", self.close_connection)
        self.connmenu.add(self.connmenu_items["disconnect"])

        self.connmenu_items["hsep"] = gtk.SeparatorMenuItem()
        self.connmenu_items["hsep"].show()
        self.connmenu.add(self.connmenu_items["hsep"])

        self.connmenu_items["details"] = gtk.ImageMenuItem(_("_Details"))
        self.connmenu_items["details"].connect("activate", self.show_host)
        self.connmenu_items["details"].show()
        self.connmenu.add(self.connmenu_items["details"])

        self.connmenu.show()

        self.window.signal_autoconnect({
            "on_menu_view_stats_disk_toggled" :     (self.stats_toggled,
                                                     cfg.STATS_DISK),
            "on_menu_view_stats_network_toggled" :  (self.stats_toggled,
                                                     cfg.STATS_NETWORK),
            "on_menu_view_stats_cpu_toggled" :      (self.stats_toggled,
                                                     cfg.STATS_CPU),

            "on_vm_manager_delete_event": self.close,
            "on_menu_file_add_connection_activate": self.new_connection,
            "on_menu_file_quit_activate": self.exit_app,
            "on_menu_file_close_activate": self.close,
            "on_menu_restore_saved_activate": self.restore_saved,
            "on_vmm_close_clicked": self.close,
            "on_vm_open_clicked": self.open_vm_console,
            "on_vm_run_clicked": self.start_vm,
            "on_vm_new_clicked": self.new_vm,
            "on_vm_shutdown_clicked": self.poweroff_vm,
            "on_vm_pause_clicked": self.pause_vm_button,
            "on_menu_edit_details_activate": self.open_vm_console,
            "on_menu_edit_delete_activate": self.delete_vm,
            "on_menu_host_details_activate": self.show_host,

            "on_vm_list_row_activated": self.open_vm_console,
            "on_vm_list_row_expanded": self.row_expanded,
            "on_vm_list_row_collapsed": self.row_collapsed,
            "on_vm_list_button_press_event": self.popup_vm_menu,

            "on_menu_edit_preferences_activate": self.show_preferences,
            "on_menu_help_about_activate": self.show_about,
            "on_menu_help_activate": self.show_help,
            })

        self.vm_selected(None)
        self.window.get_widget("vm-list").get_selection().connect("changed", self.vm_selected)

        # Initialize stat polling columns based on global polling
        # preferences (we want signal handlers for this)
        for typ, init_val in \
            [ (cfg.STATS_DISK,
               self.config.get_stats_enable_disk_poll()),
              (cfg.STATS_NETWORK,
               self.config.get_stats_enable_net_poll())]:
            self.enable_polling(None, None, init_val, typ)

        self.window.get_widget("menu_file_restore_saved").set_sensitive(False)

        self.engine.connect("connection-added", self._add_connection)
        self.engine.connect("connection-removed", self._remove_connection)

        # Select first list entry
        vmlist = self.window.get_widget("vm-list")
        if len(vmlist.get_model()) == 0:
            self.startup_error = _("Could not populate a default connection. "
                                   "Make sure the appropriate virtualization "
                                   "packages are installed (kvm, qemu, etc.) "
                                   "and that libvirtd has been restarted to "
                                   "notice the changes.\n\n"
                                   "A hypervisor connection can be manually "
                                   "added via \nFile->Add Connection")
        else:
            vmlist.get_selection().select_iter(vmlist.get_model().get_iter_first())

    def show(self):
        win = self.window.get_widget("vmm-manager")
        if self.is_visible():
            win.present()
            return
        win.show_all()
        self.engine.increment_window_counter()

        if self.startup_error:
            self.err.val_err(_("Error determining default hypervisor."),
                             self.startup_error, _("Startup Error"))
            self.startup_error = None

    def close(self, src=None, src2=None):
        if self.is_visible():
            win = self.window.get_widget("vmm-manager")
            win.hide()
            self.engine.decrement_window_counter()
            return 1

    def is_visible(self):
        if self.window.get_widget("vmm-manager").flags() & gtk.VISIBLE:
            return 1
        return 0

    def exit_app(self, src=None, src2=None):
        self.emit("action-exit-app")

    def new_connection(self, src=None):
        self.emit("action-show-connect")

    def vm_row_key(self, vm):
        return vm.get_uuid() + ":" + vm.get_connection().get_uri()

    def restore_saved(self, src=None):
        conn = self.current_connection()
        if conn.is_remote():
            self.err.val_err(_("Restoring virtual machines over remote "
                               "connections is not yet supported"))
            return

        path = util.browse_local(self.window.get_widget("vmm-manager"),
                                 _("Restore Virtual Machine"),
                                 self.config, conn,
                                 browse_reason=self.config.CONFIG_DIR_RESTORE)

        if not path:
            return

        if not conn.is_valid_saved_image(path):
            self.err.val_err(_("The file '%s' does not appear to be a "
                               "valid saved machine image") % path)
            return

        progWin = vmmAsyncJob(self.config, self.restore_saved_callback,
                              [path], _("Restoring Virtual Machine"))
        progWin.run()
        error, details = progWin.get_error()

        if error is not None:
            self.err.show_err(error, details,
                              title=_("Error restoring domain"))

    def restore_saved_callback(self, file_to_load, asyncjob):
        try:
            newconn = util.dup_conn(self.config, self.current_connection(),
                                    return_conn_class=True)
            newconn.restore(file_to_load)
        except Exception, e:
            err = (_("Error restoring domain '%s': %s") %
                                  (file_to_load, str(e)))
            details = "".join(traceback.format_exc())
            asyncjob.set_error(err, details)


    def vm_added(self, connection, uri, vmuuid):
        vm = connection.get_vm(vmuuid)
        vm.connect("status-changed", self.vm_status_changed)
        vm.connect("resources-sampled", self.vm_resources_sampled)

        vmlist = self.window.get_widget("vm-list")
        model = vmlist.get_model()

        self._append_vm(model, vm, connection)

    def vm_started(self, connection, uri, vmuuid):
        vm = connection.get_vm(vmuuid)
        logging.debug("VM %s started" % vm.get_name())
        if self.config.get_console_popup() == 2 and not vm.is_management_domain():
            # user has requested consoles on all vms
            (gtype, ignore, ignore, ignore, ignore) = vm.get_graphics_console()
            if gtype == "vnc":
                self.emit("action-show-console", uri, vmuuid)
            elif not connection.is_remote():
                self.emit("action-show-terminal", uri, vmuuid)
        else:
            self.emit("action-refresh-console", uri, vmuuid)

    def _append_vm(self, model, vm, conn):
        parent = self.rows[conn.get_uri()].iter
        row = []
        row.insert(ROW_HANDLE, vm)
        row.insert(ROW_NAME, vm.get_name())
        row.insert(ROW_MARKUP, row[ROW_NAME])
        row.insert(ROW_STATUS, vm.run_status())
        row.insert(ROW_STATUS_ICON, vm.run_status_icon())
        row.insert(ROW_KEY, vm.get_uuid())
        row.insert(ROW_HINT, None)
        row.insert(ROW_IS_CONN, False)
        row.insert(ROW_IS_CONN_CONNECTED, True)
        row.insert(ROW_IS_VM, True)
        row.insert(ROW_IS_VM_RUNNING, vm.is_active())
        row.insert(ROW_COLOR, "white")

        _iter = model.append(parent, row)
        path = model.get_path(_iter)
        self.rows[self.vm_row_key(vm)] = model[path]
        # Expand a connection when adding a vm to it
        self.window.get_widget("vm-list").expand_row(model.get_path(parent), False)

    def _append_connection(self, model, conn):
        row = []
        row.insert(ROW_HANDLE, conn)
        row.insert(ROW_NAME, conn.get_pretty_desc_inactive(False))
        if conn.state == conn.STATE_DISCONNECTED:
            markup = ("<span font='9.5' color='#5b5b5b'>%s - "
                      "Not Connected</span>" % row[ROW_NAME])
        else:
            markup = ("<span font='9.5'>%s</span>" % row[ROW_NAME])
        row.insert(ROW_MARKUP, markup)
        row.insert(ROW_STATUS, ("<span font='9'>%s</span>" %
                                conn.get_state_text()))
        row.insert(ROW_STATUS_ICON, None)
        row.insert(ROW_KEY, conn.get_uri())
        row.insert(ROW_HINT, conn.get_uri())
        row.insert(ROW_IS_CONN, True)
        row.insert(ROW_IS_CONN_CONNECTED,
                   conn.state != conn.STATE_DISCONNECTED)
        row.insert(ROW_IS_VM, False)
        row.insert(ROW_IS_VM_RUNNING, False)
        row.insert(ROW_COLOR, "#d4d2d2")

        _iter = model.append(None, row)
        path = model.get_path(_iter)
        self.rows[conn.get_uri()] = model[path]
        return _iter

    def vm_removed(self, connection, uri, vmuuid):
        vmlist = self.window.get_widget("vm-list")
        model = vmlist.get_model()

        parent = self.rows[connection.get_uri()].iter
        for row in range(model.iter_n_children(parent)):
            vm = model.get_value(model.iter_nth_child(parent, row), ROW_HANDLE)
            if vm.get_uuid() == vmuuid:
                model.remove(model.iter_nth_child(parent, row))
                del self.rows[self.vm_row_key(vm)]
                break

    def vm_status_changed(self, vm, status):
        parent = self.rows[vm.get_connection().get_uri()].iter

        vmlist = self.window.get_widget("vm-list")
        model = vmlist.get_model()

        missing = True
        for row in range(model.iter_n_children(parent)):
            _iter = model.iter_nth_child(parent, row)
            if model.get_value(_iter, ROW_KEY) == vm.get_uuid():
                missing = False
                break

        if missing:
            self._append_vm(model, vm, vm.get_connection())

        # Update run/shutdown/pause button states
        self.vm_selected()

    def vm_resources_sampled(self, vm):
        vmlist = self.window.get_widget("vm-list")
        model = vmlist.get_model()

        if not self.rows.has_key(self.vm_row_key(vm)):
            return

        row = self.rows[self.vm_row_key(vm)]
        row[ROW_STATUS] = vm.run_status()
        row[ROW_STATUS_ICON] = vm.run_status_icon()
        row[ROW_IS_VM_RUNNING] = vm.is_active()
        model.row_changed(row.path, row.iter)


    def conn_state_changed(self, conn):
        self.conn_refresh_resources(conn)
        self.vm_selected()

    def conn_refresh_resources(self, conn):
        vmlist = self.window.get_widget("vm-list")
        model = vmlist.get_model()
        row = self.rows[conn.get_uri()]

        if conn.state == conn.STATE_DISCONNECTED:
            markup = ("<span font='9.5' color='#5b5b5b'>%s - "
                      "Not Connected</span>" % row[ROW_NAME])
        else:
            markup = ("<span font='9.5'>%s</span>" % row[ROW_NAME])
        row[ROW_MARKUP] = markup
        row[ROW_STATUS] = "<span font='9'>%s</span>" % conn.get_state_text()
        row[ROW_IS_CONN_CONNECTED] = conn.state != conn.STATE_DISCONNECTED

        if conn.get_state() in [vmmConnection.STATE_DISCONNECTED,
                                vmmConnection.STATE_CONNECTING]:
            # Connection went inactive, delete any VM child nodes
            parent = self.rows[conn.get_uri()].iter
            if parent is not None:
                child = model.iter_children(parent)
                while child is not None:
                    del self.rows[self.vm_row_key(model.get_value(child, ROW_HANDLE))]
                    model.remove(child)
                    child = model.iter_children(parent)
        model.row_changed(row.path, row.iter)

    def current_vm(self):
        vmlist = self.window.get_widget("vm-list")
        selection = vmlist.get_selection()
        active = selection.get_selected()
        # check that something is selected and that it is a vm, not a connection
        if active[1] != None and active[0].iter_parent(active[1]) != None:
            return active[0].get_value(active[1], ROW_HANDLE)
        return None

    def current_connection(self):
        # returns a uri
        vmlist = self.window.get_widget("vm-list")
        selection = vmlist.get_selection()
        active = selection.get_selected()
        if active[1] != None:
            parent = active[0].iter_parent(active[1])
            # return the connection of the currently selected vm, or the
            # currently selected connection
            if parent is not None:
                return active[0].get_value(parent, ROW_HANDLE)
            else:
                return active[0].get_value(active[1], ROW_HANDLE)
        return None

    def current_vmuuid(self):
        vm = self.current_vm()
        if vm is None:
            return None
        return vm.get_uuid()

    def current_connection_uri(self):
        conn = self.current_connection()
        if conn is None:
            return None
        return conn.get_uri()

    def show_vm_details(self,ignore):
        conn = self.current_connection()
        if conn is None:
            return
        vm = self.current_vm()
        if vm is None:
            self.emit("action-show-host", conn.get_uri())
        else:
            self.emit("action-show-console", conn.get_uri(), self.current_vmuuid())

    def close_connection(self, ignore):
        conn = self.current_connection()
        if conn.get_state() != vmmConnection.STATE_DISCONNECTED:
            conn.close()

    def open_connection(self, ignore = None):
        conn = self.current_connection()
        if conn.get_state() == vmmConnection.STATE_DISCONNECTED:
            conn.open()

    def open_vm_console(self,ignore,ignore2=None,ignore3=None):
        if self.current_vmuuid():
            self.emit("action-show-console", self.current_connection_uri(), self.current_vmuuid())
        elif self.current_connection():
            self.open_connection()

    def open_clone_window(self, ignore1=None, ignore2=None, ignore3=None):
        if self.current_vmuuid():
            self.emit("action-clone-domain", self.current_connection_uri(),
                      self.current_vmuuid())

    def vm_selected(self, ignore=None):
        conn = self.current_connection()
        vm = self.current_vm()

        show_open = bool(vm)
        show_details = bool(vm)
        host_details = bool(vm or conn)
        delete = bool((vm and vm.is_runable()) or conn)
        show_run = bool(vm and vm.is_runable())
        is_paused = bool(vm and vm.is_paused())
        if is_paused:
            show_pause = bool(vm and vm.is_unpauseable())
        else:
            show_pause = bool(vm and vm.is_pauseable())
        show_shutdown = bool(vm and vm.is_stoppable())
        restore = bool(conn and conn.get_state() == vmmConnection.STATE_ACTIVE)

        self.window.get_widget("vm-open").set_sensitive(show_open)
        self.window.get_widget("vm-run").set_sensitive(show_run)
        self.window.get_widget("vm-shutdown").set_sensitive(show_shutdown)
        self.set_pause_state(is_paused)
        self.window.get_widget("vm-pause").set_sensitive(show_pause)

        self.window.get_widget("menu_edit_details").set_sensitive(show_details)
        self.window.get_widget("menu_host_details").set_sensitive(host_details)
        self.window.get_widget("menu_edit_delete").set_sensitive(delete)
        self.window.get_widget("menu_file_restore_saved").set_sensitive(restore)


    def popup_vm_menu(self, widget, event):
        tup = widget.get_path_at_pos(int(event.x), int(event.y))
        if tup == None:
            return False
        path = tup[0]
        model = widget.get_model()
        _iter = model.get_iter(path)
        if model.iter_parent(_iter) != None:
            # a vm is selected, retrieve it from the first column of the model
            vm = model.get_value(_iter, ROW_HANDLE)
            if event.button == 3:
                # Update popup menu based upon vm status
                if vm.is_read_only() == True:
                    self.vmmenu_items["run"].set_sensitive(False)
                    self.vmmenu_items["pause"].set_sensitive(False)
                    self.vmmenu_items["pause"].show()
                    self.vmmenu_items["resume"].hide()
                    self.vmmenu_items["resume"].set_sensitive(False)
                    self.vmmenu_items["shutdown"].set_sensitive(False)
                    self.vmmenu_items["migrate"].set_sensitive(False)
                else:
                    if vm.status() == libvirt.VIR_DOMAIN_SHUTOFF:
                        self.vmmenu_items["run"].set_sensitive(True)
                        self.vmmenu_items["pause"].set_sensitive(False)
                        self.vmmenu_items["pause"].show()
                        self.vmmenu_items["resume"].hide()
                        self.vmmenu_items["resume"].set_sensitive(False)
                        self.vmmenu_items["shutdown"].set_sensitive(False)
                        self.vmmenu_items["migrate"].set_sensitive(True)
                    elif vm.status() == libvirt.VIR_DOMAIN_RUNNING:
                        self.vmmenu_items["run"].set_sensitive(False)
                        self.vmmenu_items["pause"].set_sensitive(True)
                        self.vmmenu_items["pause"].show()
                        self.vmmenu_items["resume"].hide()
                        self.vmmenu_items["resume"].set_sensitive(False)
                        self.vmmenu_items["shutdown"].set_sensitive(True)
                        self.vmmenu_items["migrate"].set_sensitive(True)
                    elif vm.status() == libvirt.VIR_DOMAIN_PAUSED:
                        self.vmmenu_items["run"].set_sensitive(False)
                        self.vmmenu_items["pause"].hide()
                        self.vmmenu_items["pause"].set_sensitive(False)
                        self.vmmenu_items["resume"].show()
                        self.vmmenu_items["resume"].set_sensitive(True)
                        self.vmmenu_items["shutdown"].set_sensitive(True)
                        self.vmmenu_items["migrate"].set_sensitive(True)
                self.vmmenu.popup(None, None, None, 0, event.time)
            return False
        else:
            conn = model.get_value(_iter, ROW_HANDLE)
            if event.button == 3:
                if conn.get_state() != vmmConnection.STATE_DISCONNECTED:
                    self.connmenu_items["create"].set_sensitive(True)
                    self.connmenu_items["disconnect"].set_sensitive(True)
                    self.connmenu_items["connect"].set_sensitive(False)
                else:
                    self.connmenu_items["create"].set_sensitive(False)
                    self.connmenu_items["disconnect"].set_sensitive(False)
                    self.connmenu_items["connect"].set_sensitive(True)
                self.connmenu.popup(None, None, None, 0, event.time)
            return False

    def new_vm(self, ignore=None):
        self.emit("action-show-create", self.current_connection_uri())

    def delete_vm(self, ignore=None):
        conn = self.current_connection()
        vm = self.current_vm()
        if vm is None:
            self._do_delete_connection(conn)
        else:
            self._do_delete_vm(vm)

    def _do_delete_connection(self, conn):
        if conn is None:
            return

        result = self.err.yes_no(_("This will remove the connection:\n\n%s\n\n"
                                   "Are you sure?") % conn.get_uri())
        if not result:
            return
        self.engine.remove_connection(conn.get_uri())

    def _do_delete_vm(self, vm):
        if vm.is_active():
            return

        if not self.delete_dialog:
            self.delete_dialog = vmmDeleteDialog(self.config, vm)
        else:
            self.delete_dialog.set_vm(vm)

        self.delete_dialog.show()

    def show_about(self, src):
        self.emit("action-show-about")

    def show_help(self, src):
        # From the manager window, show the help document from the beginning
        self.emit("action-show-help", None) #No 'id', load the front page

    def show_preferences(self, src):
        self.emit("action-show-preferences")

    def show_host(self, src):
        self.emit("action-show-host", self.current_connection_uri())

    def prepare_vmlist(self):
        vmlist = self.window.get_widget("vm-list")

        # Handle, name, markup, status, status icon, key/uuid, hint, is conn,
        # is conn connected, is vm, is vm running, color
        model = gtk.TreeStore(object, str, str, str, gtk.gdk.Pixbuf, str, str,
                              bool, bool, bool, bool, str)
        vmlist.set_model(model)
        util.tooltip_wrapper(vmlist, ROW_HINT, "set_tooltip_column")

        vmlist.set_headers_visible(True)
        vmlist.set_level_indentation(-15)

        nameCol = gtk.TreeViewColumn(_("Name"))
        nameCol.set_expand(True)
        nameCol.set_spacing(12)
        cpuUsageCol = gtk.TreeViewColumn(_("CPU usage"))
        cpuUsageCol.set_min_width(150)

        statusCol = nameCol
        vmlist.append_column(nameCol)
        vmlist.append_column(cpuUsageCol)

        # For the columns which follow, we deliberately bind columns
        # to fields in the list store & on each update copy the info
        # out of the vmmDomain object into the store. Although this
        # sounds foolish, empirically this is faster than using the
        # set_cell_data_func() callbacks to pull the data out of
        # vmmDomain on demand. I suspect this is because the latter
        # needs to do many transitions  C<->Python for callbacks
        # which are relatively slow.

        status_icon = gtk.CellRendererPixbuf()
        statusCol.pack_start(status_icon, False)
        statusCol.add_attribute(status_icon, 'cell-background', ROW_COLOR)
        statusCol.add_attribute(status_icon, 'pixbuf', ROW_STATUS_ICON)
        statusCol.add_attribute(status_icon, 'visible', ROW_IS_VM)
        statusCol.add_attribute(status_icon, 'sensitive', ROW_IS_VM_RUNNING)

        name_txt = gtk.CellRendererText()
        nameCol.pack_start(name_txt, True)
        nameCol.add_attribute(name_txt, 'cell-background', ROW_COLOR)
        nameCol.add_attribute(name_txt, 'markup', ROW_MARKUP)
        nameCol.set_sort_column_id(VMLIST_SORT_NAME)

        cpuUsage_txt = gtk.CellRendererText()
        cpuUsage_img = CellRendererSparkline()
        cpuUsage_img.set_property("xpad", 6)
        cpuUsage_img.set_property("ypad", 12)
        cpuUsage_img.set_property("reversed", True)
        cpuUsageCol.pack_start(cpuUsage_img, True)
        cpuUsageCol.pack_start(cpuUsage_txt, False)
        cpuUsageCol.add_attribute(cpuUsage_img, 'cell-background', ROW_COLOR)
        cpuUsageCol.add_attribute(cpuUsage_img, 'visible', ROW_IS_VM)
        cpuUsageCol.add_attribute(cpuUsage_txt, 'cell-background', ROW_COLOR)
        cpuUsageCol.add_attribute(cpuUsage_txt, 'visible', ROW_IS_CONN)
        cpuUsageCol.set_sort_column_id(VMLIST_SORT_STATS)
        self.stats_sparkline = cpuUsage_img
        self.stats_column = cpuUsageCol
        self.stats_toggled(None, self.get_stats_type())

        model.set_sort_func(VMLIST_SORT_NAME, self.vmlist_name_sorter)

        model.set_sort_column_id(VMLIST_SORT_NAME, gtk.SORT_ASCENDING)

    def vmlist_name_sorter(self, model, iter1, iter2):
        return cmp(model.get_value(iter1, ROW_NAME),
                   model.get_value(iter2, ROW_NAME))

    def vmlist_cpu_usage_sorter(self, model, iter1, iter2):
        return cmp(model.get_value(iter1, ROW_HANDLE).cpu_time_percentage(), model.get_value(iter2, ROW_HANDLE).cpu_time_percentage())

    def vmlist_disk_io_sorter(self, model, iter1, iter2):
        return cmp(model.get_value(iter1, ROW_HANDLE).disk_io_rate(), model.get_value(iter2, ROW_HANDLE).disk_io_rate())

    def vmlist_network_usage_sorter(self, model, iter1, iter2):
        return cmp(model.get_value(iter1, ROW_HANDLE).network_traffic_rate(), model.get_value(iter2, ROW_HANDLE).network_traffic_rate())

    def enable_polling(self, ignore1, ignore2, conf_entry, userdata):
        if userdata == cfg.STATS_DISK:
            widgn = "menu_view_stats_disk"
        elif userdata == cfg.STATS_NETWORK:
            widgn = "menu_view_stats_network"
        widget = self.window.get_widget(widgn)

        tool_text = ""
        if conf_entry and (conf_entry == True or \
                           conf_entry.get_value().get_bool()):
            widget.set_sensitive(True)
        else:
            if widget.get_active():
                widget.set_active(False)
            widget.set_sensitive(False)
            tool_text = _("Disabled in preferences dialog.")

            if self.get_stats_type() == userdata:
                # Switch graphs over to guaranteed safe value
                self.stats_toggled(None, cfg.STATS_CPU)

        util.tooltip_wrapper(widget, tool_text)

    def stats_toggled_config(self, ignore1, ignore2, conf_entry, ignore4):
        self.stats_toggled(None, conf_entry.get_value().get_int())

    def get_stats_type(self):
        return self.config.get_vmlist_stats_type()

    def stats_toggled(self, src, stats_id):
        if src and not src.get_active():
            return

        if stats_id == cfg.STATS_NETWORK:
            column_name = _("Network I/O")
            stats_func = self.network_traffic_img
            sort_func = self.vmlist_network_usage_sorter
            widg = "menu_view_stats_network"
        elif stats_id == cfg.STATS_DISK:
            column_name = _("Disk I/O")
            stats_func = self.disk_io_img
            sort_func = self.vmlist_disk_io_sorter
            widg = "menu_view_stats_disk"
        elif stats_id == cfg.STATS_CPU:
            column_name = _("CPU Usage")
            stats_func = self.cpu_usage_img
            sort_func = self.vmlist_cpu_usage_sorter
            widg = "menu_view_stats_cpu"
        else:
            return

        if not src:
            self.window.get_widget(widg).set_active(True)

        if self.stats_column:
            vmlist = self.window.get_widget("vm-list")
            model = vmlist.get_model()
            self.stats_column.set_title(column_name)
            self.stats_column.set_cell_data_func(self.stats_sparkline,
                                                 stats_func, None)
            model.set_sort_func(VMLIST_SORT_STATS, sort_func)

        if stats_id != self.get_stats_type():
            self.config.set_vmlist_stats_type(stats_id)

    def cpu_usage_img(self,  column, cell, model, _iter, data):
        if model.get_value(_iter, ROW_HANDLE) is None:
            return
        data = model.get_value(_iter, ROW_HANDLE).cpu_time_vector_limit(40)
        cell.set_property('data_array', data)

    def disk_io_img(self,  column, cell, model, _iter, data):
        if model.get_value(_iter, ROW_HANDLE) is None:
            return
        data = model.get_value(_iter, ROW_HANDLE).disk_io_vector_limit(40)
        cell.set_property('data_array', data)

    def network_traffic_img(self,  column, cell, model, _iter, data):
        if model.get_value(_iter, ROW_HANDLE) is None:
            return
        data = model.get_value(_iter, ROW_HANDLE).network_traffic_vector_limit(40)
        cell.set_property('data_array', data)

    def set_pause_state(self, state):
        src = self.window.get_widget("vm-pause")
        try:
            self.ignore_pause = True
            src.set_active(state)
        finally:
            self.ignore_pause = False

    def pause_vm_button(self, src):
        if self.ignore_pause:
            return

        do_pause = src.get_active()

        if do_pause:
            self.pause_vm(None)
        else:
            self.resume_vm(None)

        # Set button state back to original value: just let the status
        # update function fix things for us
        self.set_pause_state(not do_pause)

    def start_vm(self, ignore):
        vm = self.current_vm()
        if vm is not None:
            self.emit("action-run-domain", vm.get_connection().get_uri(), vm.get_uuid())

    def reboot_vm(self, ignore):
        vm = self.current_vm()
        if vm is not None:
            self.emit("action-reboot-domain", vm.get_connection().get_uri(), vm.get_uuid())

    def poweroff_vm(self, ignore):
        vm = self.current_vm()
        if vm is not None:
            self.emit("action-shutdown-domain", vm.get_connection().get_uri(), vm.get_uuid())

    def destroy_vm(self, ignore):
        vm = self.current_vm()
        if vm is not None:
            self.emit("action-destroy-domain", vm.get_connection().get_uri(), vm.get_uuid())

    def pause_vm(self, ignore):
        vm = self.current_vm()
        if vm is not None:
            self.emit("action-suspend-domain", vm.get_connection().get_uri(), vm.get_uuid())

    def resume_vm(self, ignore):
        vm = self.current_vm()
        if vm is not None:
            self.emit("action-resume-domain", vm.get_connection().get_uri(), vm.get_uuid())

    def migrate(self, ignore, uri):
        vm = self.current_vm()
        if vm is not None:
            self.emit("action-migrate-domain", vm.get_connection().get_uri(),
                      vm.get_uuid(), uri)

    def populate_migrate_submenu(self, src):
        vm = self.current_vm()
        if not vm:
            return

        self.engine.populate_migrate_menu(self.vmmenumigrate, self.migrate,
                                          vm)

    def _add_connection(self, engine, conn):
        conn.connect("vm-added", self.vm_added)
        conn.connect("vm-removed", self.vm_removed)
        conn.connect("resources-sampled", self.conn_refresh_resources)
        conn.connect("state-changed", self.conn_state_changed)
        conn.connect("connect-error", self._connect_error)
        conn.connect("vm-started", self.vm_started)
        # add the connection to the treeModel
        vmlist = self.window.get_widget("vm-list")
        if not self.rows.has_key(conn.get_uri()):
            row = self._append_connection(vmlist.get_model(), conn)
            vmlist.get_selection().select_iter(row)

    def _remove_connection(self, engine, conn):
        model = self.window.get_widget("vm-list").get_model()
        parent = self.rows[conn.get_uri()].iter
        if parent is not None:
            child = model.iter_children(parent)
            while child is not None:
                del self.rows[self.vm_row_key(model.get_value(child, ROW_HANDLE))]
                model.remove(child)
                child = model.iter_children(parent)
            model.remove(parent)
            del self.rows[conn.get_uri()]

    def row_expanded(self, treeview, _iter, path):
        conn = treeview.get_model().get_value(_iter, ROW_HANDLE)
        conn.resume()

    def row_collapsed(self, treeview, _iter, path):
        conn = treeview.get_model().get_value(_iter, ROW_HANDLE)
        conn.pause()

    def _connect_error(self, conn, details):
        if conn.get_driver() == "xen" and not conn.is_remote():
            self.err.show_err(_("Unable to open a connection to the Xen hypervisor/daemon.\n\n" +
                              "Verify that:\n" +
                              " - A Xen host kernel was booted\n" +
                              " - The Xen service has been started\n"),
                              details,
                              title=_("Virtual Machine Manager Connection Failure"))
        else:
            self.err.show_err(_("Unable to open a connection to the libvirt "
                                "management daemon.\n\n" +
                                "Libvirt URI is: %s\n\n" % conn.get_uri() +
                                "Verify that:\n" +
                                " - The 'libvirtd' daemon has been started\n"),
                              details,
                              title=_("Virtual Machine Manager Connection "
                                      "Failure"))

gobject.type_register(vmmManager)

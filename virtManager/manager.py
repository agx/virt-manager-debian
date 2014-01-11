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

import logging
import re

# pylint: disable=E0611
from gi.repository import GObject
from gi.repository import Gtk
from gi.repository import Gdk
from gi.repository import GdkPixbuf
# pylint: enable=E0611

from virtManager import packageutils
from virtManager import uihelpers
from virtManager.connection import vmmConnection
from virtManager.baseclass import vmmGObjectUI
from virtManager.graphwidgets import CellRendererSparkline
from virtManager import util as util


# Number of data points for performance graphs
GRAPH_LEN = 40

# fields in the tree model data set
(ROW_HANDLE,
ROW_NAME,
ROW_MARKUP,
ROW_STATUS,
ROW_STATUS_ICON,
ROW_KEY,
ROW_HINT,
ROW_IS_CONN,
ROW_IS_CONN_CONNECTED,
ROW_IS_VM,
ROW_IS_VM_RUNNING,
ROW_COLOR,
ROW_INSPECTION_OS_ICON) = range(13)

# Columns in the tree view
COL_NAME = 0
COL_GUEST_CPU = 1
COL_HOST_CPU = 2
COL_DISK = 3
COL_NETWORK = 4


try:
    import gi
    gi.check_version("3.7.4")
    can_set_row_none = True
except (ValueError, AttributeError):
    can_set_row_none = False


def _style_get_prop(widget, propname):
    value = GObject.Value()
    value.init(GObject.TYPE_INT)
    widget.style_get_property(propname, value)
    return value.get_int()


class vmmManager(vmmGObjectUI):
    __gsignals__ = {
        "action-show-connect": (GObject.SignalFlags.RUN_FIRST, None, []),
        "action-show-vm": (GObject.SignalFlags.RUN_FIRST, None, [str, str]),
        "action-show-about": (GObject.SignalFlags.RUN_FIRST, None, []),
        "action-show-host": (GObject.SignalFlags.RUN_FIRST, None, [str]),
        "action-show-preferences": (GObject.SignalFlags.RUN_FIRST, None, []),
        "action-show-create": (GObject.SignalFlags.RUN_FIRST, None, [str]),
        "action-suspend-domain": (GObject.SignalFlags.RUN_FIRST, None, [str, str]),
        "action-resume-domain": (GObject.SignalFlags.RUN_FIRST, None, [str, str]),
        "action-run-domain": (GObject.SignalFlags.RUN_FIRST, None, [str, str]),
        "action-shutdown-domain": (GObject.SignalFlags.RUN_FIRST, None, [str, str]),
        "action-reset-domain": (GObject.SignalFlags.RUN_FIRST, None, [str, str]),
        "action-reboot-domain": (GObject.SignalFlags.RUN_FIRST, None, [str, str]),
        "action-destroy-domain": (GObject.SignalFlags.RUN_FIRST, None, [str, str]),
        "action-save-domain": (GObject.SignalFlags.RUN_FIRST, None, [str, str]),
        "action-migrate-domain": (GObject.SignalFlags.RUN_FIRST, None, [str, str]),
        "action-delete-domain": (GObject.SignalFlags.RUN_FIRST, None, [str, str]),
        "action-clone-domain": (GObject.SignalFlags.RUN_FIRST, None, [str, str]),
        "action-exit-app": (GObject.SignalFlags.RUN_FIRST, None, []),
        "manager-closed": (GObject.SignalFlags.RUN_FIRST, None, []),
        "manager-opened": (GObject.SignalFlags.RUN_FIRST, None, []),
        "remove-conn": (GObject.SignalFlags.RUN_FIRST, None, [str]),
        "add-default-conn": (GObject.SignalFlags.RUN_FIRST, None, []),
    }

    def __init__(self):
        vmmGObjectUI.__init__(self, "vmm-manager.ui", "vmm-manager")

        self.ignore_pause = False

        # Mapping of VM UUID -> tree model rows to
        # allow O(1) access instead of O(n)
        self.rows = {}

        w, h = self.config.get_manager_window_size()
        self.topwin.set_default_size(w or 550, h or 550)
        self.prev_position = None

        self.vmmenu = Gtk.Menu()
        self.vmmenushutdown = Gtk.Menu()
        self.vmmenu_items = {}
        self.vmmenushutdown_items = {}
        self.connmenu = Gtk.Menu()
        self.connmenu_items = {}

        # There seem to be ref counting issues with calling
        # list.get_column, so avoid it
        self.diskcol = None
        self.netcol = None
        self.guestcpucol = None
        self.hostcpucol = None

        self.builder.connect_signals({
            "on_menu_view_guest_cpu_usage_activate":
                    self.toggle_stats_visible_guest_cpu,
            "on_menu_view_host_cpu_usage_activate":
                    self.toggle_stats_visible_host_cpu,
            "on_menu_view_disk_io_activate" :
                    self.toggle_stats_visible_disk,
            "on_menu_view_network_traffic_activate":
                    self.toggle_stats_visible_network,

            "on_vm_manager_delete_event": self.close,
            "on_vmm_manager_configure_event": self.window_resized,
            "on_menu_file_add_connection_activate": self.new_conn,
            "on_menu_file_quit_activate": self.exit_app,
            "on_menu_file_close_activate": self.close,
            "on_vmm_close_clicked": self.close,
            "on_vm_open_clicked": self.show_vm,
            "on_vm_run_clicked": self.start_vm,
            "on_vm_new_clicked": self.new_vm,
            "on_vm_shutdown_clicked": self.poweroff_vm,
            "on_vm_pause_clicked": self.pause_vm_button,
            "on_menu_edit_details_activate": self.show_vm,
            "on_menu_edit_delete_activate": self.do_delete,
            "on_menu_host_details_activate": self.show_host,

            "on_vm_list_row_activated": self.show_vm,
            "on_vm_list_button_press_event": self.popup_vm_menu_button,
            "on_vm_list_key_press_event": self.popup_vm_menu_key,

            "on_menu_edit_preferences_activate": self.show_preferences,
            "on_menu_help_about_activate": self.show_about,
        })

        self.init_vmlist()
        self.init_stats()
        self.init_toolbar()
        self.init_context_menus()

        self.vm_selected()
        self.widget("vm-list").get_selection().connect("changed",
                                                       self.vm_selected)

        self.max_disk_rate = 10.0
        self.max_net_rate = 10.0

        # Initialize stat polling columns based on global polling
        # preferences (we want signal handlers for this)
        self.enable_polling(COL_DISK)
        self.enable_polling(COL_NETWORK)

        # Select first list entry
        vmlist = self.widget("vm-list")
        if len(vmlist.get_model()) != 0:
            vmlist.get_selection().select_iter(
                                        vmlist.get_model().get_iter_first())

        # Queue up the default connection detector
        self.idle_emit("add-default-conn")

    ##################
    # Common methods #
    ##################

    def show(self):
        vis = self.is_visible()
        self.topwin.present()
        if vis:
            return

        logging.debug("Showing manager")
        if self.prev_position:
            self.topwin.move(*self.prev_position)
            self.prev_position = None

        self.emit("manager-opened")

    def close(self, src_ignore=None, src2_ignore=None):
        if not self.is_visible():
            return

        logging.debug("Closing manager")
        self.prev_position = self.topwin.get_position()
        self.topwin.hide()
        self.emit("manager-closed")

        return 1


    def _cleanup(self):
        self.rows = None

        self.diskcol = None
        self.guestcpucol = None
        self.hostcpucol = None
        self.netcol = None

        self.vmmenu.destroy()
        self.vmmenu = None
        self.vmmenu_items = None
        self.vmmenushutdown.destroy()
        self.vmmenushutdown = None
        self.vmmenushutdown_items = None
        self.connmenu.destroy()
        self.connmenu = None
        self.connmenu_items = None

    def is_visible(self):
        return bool(self.topwin.get_visible())

    def set_startup_error(self, msg):
        self.widget("vm-notebook").set_current_page(1)
        self.widget("startup-error-label").set_text(msg)

    ################
    # Init methods #
    ################

    def init_stats(self):
        self.add_gconf_handle(
            self.config.on_vmlist_guest_cpu_usage_visible_changed(
                                self.toggle_guest_cpu_usage_visible_widget))
        self.add_gconf_handle(
            self.config.on_vmlist_host_cpu_usage_visible_changed(
                                self.toggle_host_cpu_usage_visible_widget))
        self.add_gconf_handle(
            self.config.on_vmlist_disk_io_visible_changed(
                                self.toggle_disk_io_visible_widget))
        self.add_gconf_handle(
            self.config.on_vmlist_network_traffic_visible_changed(
                                self.toggle_network_traffic_visible_widget))

        # Register callbacks with the global stats enable/disable values
        # that disable the associated vmlist widgets if reporting is disabled
        self.add_gconf_handle(
            self.config.on_stats_enable_disk_poll_changed(self.enable_polling,
                                                    COL_DISK))
        self.add_gconf_handle(
            self.config.on_stats_enable_net_poll_changed(self.enable_polling,
                                                    COL_NETWORK))


        self.widget("menu_view_stats_guest_cpu").set_active(
                            self.config.is_vmlist_guest_cpu_usage_visible())
        self.widget("menu_view_stats_host_cpu").set_active(
                            self.config.is_vmlist_host_cpu_usage_visible())
        self.widget("menu_view_stats_disk").set_active(
                            self.config.is_vmlist_disk_io_visible())
        self.widget("menu_view_stats_network").set_active(
                            self.config.is_vmlist_network_traffic_visible())

    def init_toolbar(self):
        self.widget("vm-new").set_icon_name("vm_new")
        self.widget("vm-open").set_icon_name("icon_console")
        uihelpers.build_shutdown_button_menu(self.widget("vm-shutdown"),
                                             self.poweroff_vm,
                                             self.reboot_vm,
                                             self.reset_vm,
                                             self.destroy_vm,
                                             self.save_vm)

        tool = self.widget("vm-toolbar")
        tool.set_property("icon-size", Gtk.IconSize.LARGE_TOOLBAR)
        for c in tool.get_children():
            c.set_homogeneous(False)

    def init_context_menus(self):
        def build_icon(name):
            return Gtk.Image.new_from_icon_name(name, Gtk.IconSize.MENU)

        def build_stock(name):
            return Gtk.Image.new_from_stock(name, Gtk.IconSize.MENU)

        shutdownmenu_icon   = build_icon("system-shutdown")
        reboot_icon         = build_icon("system-shutdown")
        shutdown_icon       = build_icon("system-shutdown")
        destroy_icon        = build_icon("system-shutdown")
        reset_icon          = build_icon("system-shutdown")
        run_icon            = build_stock(Gtk.STOCK_MEDIA_PLAY)
        pause_icon          = build_stock(Gtk.STOCK_MEDIA_PAUSE)
        save_icon           = build_stock(Gtk.STOCK_SAVE)
        resume_icon         = build_stock(Gtk.STOCK_MEDIA_PAUSE)
        delete_icon         = build_stock(Gtk.STOCK_DELETE)

        def add_to_menu(menu, items, idx, text, icon, cb):
            if text[0:3] == 'gtk':
                item = Gtk.ImageMenuItem.new_from_stock(text, None)
            else:
                item = Gtk.ImageMenuItem.new_with_mnemonic(text)
            if icon:
                item.set_image(icon)
            item.show()
            if cb:
                item.connect("activate", cb)
            menu.add(item)
            items[idx] = item

        def add_vm_menu(idx, text, icon, cb):
            add_to_menu(self.vmmenu, self.vmmenu_items, idx, text, icon, cb)
        def add_shutdown_menu(idx, text, icon, cb):
            add_to_menu(self.vmmenushutdown, self.vmmenushutdown_items,
                        idx, text, icon, cb)
        def add_conn_menu(idx, text, icon, cb):
            add_to_menu(self.connmenu, self.connmenu_items,
                        idx, text, icon, cb)
        def add_sep(menu, items, idx):
            sep = Gtk.SeparatorMenuItem()
            sep.show()
            menu.add(sep)
            items[idx] = sep

        # Build VM context menu
        add_vm_menu("run", _("_Run"), run_icon, self.start_vm)
        add_vm_menu("pause", _("_Pause"), pause_icon, self.pause_vm)
        add_vm_menu("resume", _("R_esume"), resume_icon, self.resume_vm)

        add_vm_menu("shutdown", _("_Shut Down"), shutdownmenu_icon, None)
        self.vmmenu_items["shutdown"].set_submenu(self.vmmenushutdown)
        add_shutdown_menu("reboot", _("_Reboot"), reboot_icon, self.reboot_vm)
        add_shutdown_menu("poweroff", _("_Shut Down"), shutdown_icon,
                          self.poweroff_vm)
        add_shutdown_menu("forcereset", _("_Force Reset"), reset_icon,
                          self.reset_vm)
        add_shutdown_menu("forcepoweroff", _("_Force Off"), destroy_icon,
                          self.destroy_vm)
        add_sep(self.vmmenushutdown, self.vmmenushutdown_items, "sep")
        add_shutdown_menu("save", _("Sa_ve"), save_icon, self.save_vm)

        add_sep(self.vmmenu, self.vmmenu_items, "hsep1")
        add_vm_menu("clone", _("_Clone..."), None, self.open_clone_window)
        add_vm_menu("migrate", _("_Migrate..."), None, self.migrate_vm)
        add_vm_menu("delete", _("_Delete"), delete_icon, self.do_delete)

        add_sep(self.vmmenu, self.vmmenu_items, "hsep2")
        add_vm_menu("open", Gtk.STOCK_OPEN, None, self.show_vm)
        self.vmmenu.show()

        # Build connection context menu
        add_conn_menu("create", Gtk.STOCK_NEW, None, self.new_vm)
        add_conn_menu("connect", Gtk.STOCK_CONNECT, None, self.open_conn)
        add_conn_menu("disconnect", Gtk.STOCK_DISCONNECT, None,
                      self.close_conn)
        add_sep(self.connmenu, self.connmenu_items, "hsep1")
        add_conn_menu("delete", Gtk.STOCK_DELETE, None, self.do_delete)
        add_sep(self.connmenu, self.connmenu_items, "hsep2")
        add_conn_menu("details", _("D_etails"), None, self.show_host)
        self.connmenu.show()

    def init_vmlist(self):
        vmlist = self.widget("vm-list")
        self.widget("vm-notebook").set_show_tabs(False)

        rowtypes = []
        rowtypes.insert(ROW_HANDLE, object)  # backing object
        rowtypes.insert(ROW_NAME, str)  # object name
        rowtypes.insert(ROW_MARKUP, str)  # row markup text
        rowtypes.insert(ROW_STATUS, str)  # object status string
        rowtypes.insert(ROW_STATUS_ICON, str)  # status icon name
        rowtypes.insert(ROW_KEY, str)  # key/uuid
        rowtypes.insert(ROW_HINT, str)  # row tooltip
        rowtypes.insert(ROW_IS_CONN, bool)  # if object is a connection
        rowtypes.insert(ROW_IS_CONN_CONNECTED, bool)  # if conn is connected
        rowtypes.insert(ROW_IS_VM, bool)  # if row is VM
        rowtypes.insert(ROW_IS_VM_RUNNING, bool)  # if VM is running
        rowtypes.insert(ROW_COLOR, str)  # row markup color string
        rowtypes.insert(ROW_INSPECTION_OS_ICON, GdkPixbuf.Pixbuf)  # OS icon

        model = Gtk.TreeStore(*rowtypes)
        vmlist.set_model(model)
        vmlist.set_tooltip_column(ROW_HINT)
        vmlist.set_headers_visible(True)
        vmlist.set_level_indentation(
                -(_style_get_prop(vmlist, "expander-size") + 3))

        nameCol = Gtk.TreeViewColumn(_("Name"))
        nameCol.set_expand(True)
        nameCol.set_spacing(6)

        statusCol = nameCol
        vmlist.append_column(nameCol)

        status_icon = Gtk.CellRendererPixbuf()
        status_icon.set_property("stock-size", Gtk.IconSize.DND)
        statusCol.pack_start(status_icon, False)
        statusCol.add_attribute(status_icon, 'icon-name', ROW_STATUS_ICON)
        statusCol.add_attribute(status_icon, 'visible', ROW_IS_VM)

        inspection_os_icon = Gtk.CellRendererPixbuf()
        statusCol.pack_start(inspection_os_icon, False)
        statusCol.add_attribute(inspection_os_icon, 'pixbuf',
                                ROW_INSPECTION_OS_ICON)
        statusCol.add_attribute(inspection_os_icon, 'visible', ROW_IS_VM)

        name_txt = Gtk.CellRendererText()
        nameCol.pack_start(name_txt, True)
        nameCol.add_attribute(name_txt, 'markup', ROW_MARKUP)
        nameCol.add_attribute(name_txt, 'foreground', ROW_COLOR)
        nameCol.set_sort_column_id(COL_NAME)

        def make_stats_column(title, datafunc, is_visible, colnum):
            col = Gtk.TreeViewColumn(title)
            col.set_min_width(140)

            txt = Gtk.CellRendererText()
            txt.set_property("ypad", 4)
            col.pack_start(txt, True)
            col.add_attribute(txt, 'visible', ROW_IS_CONN)

            img = CellRendererSparkline()
            img.set_property("xpad", 6)
            img.set_property("ypad", 12)
            img.set_property("reversed", True)
            col.pack_start(img, True)
            col.add_attribute(img, 'visible', ROW_IS_VM)
            col.set_cell_data_func(img, datafunc, None)

            col.set_visible(is_visible)
            col.set_sort_column_id(colnum)
            vmlist.append_column(col)
            return col

        self.guestcpucol = make_stats_column(_("CPU usage"),
                            self.guest_cpu_usage_img,
                            self.config.is_vmlist_guest_cpu_usage_visible(),
                            COL_GUEST_CPU)
        self.hostcpucol = make_stats_column(_("Host CPU usage"),
                            self.host_cpu_usage_img,
                            self.config.is_vmlist_host_cpu_usage_visible(),
                            COL_HOST_CPU)
        self.diskcol = make_stats_column(_("Disk I/O"),
                            self.disk_io_img,
                            self.config.is_vmlist_disk_io_visible(),
                            COL_DISK)
        self.netcol = make_stats_column(_("Network I/O"),
                            self.network_traffic_img,
                            self.config.is_vmlist_network_traffic_visible(),
                            COL_NETWORK)

        model.set_sort_func(COL_NAME, self.vmlist_name_sorter)
        model.set_sort_func(COL_GUEST_CPU, self.vmlist_guest_cpu_usage_sorter)
        model.set_sort_func(COL_HOST_CPU, self.vmlist_host_cpu_usage_sorter)
        model.set_sort_func(COL_DISK, self.vmlist_disk_io_sorter)
        model.set_sort_func(COL_NETWORK, self.vmlist_network_usage_sorter)
        model.set_sort_column_id(COL_NAME, Gtk.SortType.ASCENDING)

    ##################
    # Helper methods #
    ##################

    def current_row(self):
        vmlist = self.widget("vm-list")
        selection = vmlist.get_selection()
        active = selection.get_selected()

        treestore, treeiter = active
        if treeiter is not None:
            return treestore[treeiter]
        return None

    def current_vm(self):
        row = self.current_row()
        if not row or row[ROW_IS_CONN]:
            return None

        return row[ROW_HANDLE]

    def current_conn(self):
        row = self.current_row()
        if not row:
            return None

        handle = row[ROW_HANDLE]
        if row[ROW_IS_CONN]:
            return handle
        else:
            return handle.conn

    def current_vmuuid(self):
        vm = self.current_vm()
        if vm is None:
            return None
        return vm.get_uuid()

    def current_conn_uri(self, default_selection=False):
        vmlist = self.widget("vm-list")
        model = vmlist.get_model()

        conn = self.current_conn()
        if conn is None and default_selection:
            # Nothing selected, use first connection row
            for row in model:
                if row[ROW_IS_CONN]:
                    conn = row[ROW_HANDLE]
                    break

        if conn:
            return conn.get_uri()
        return None

    ####################
    # Action listeners #
    ####################

    def window_resized(self, ignore, event):
        # Sometimes dimensions change when window isn't visible
        if not self.is_visible():
            return

        self.config.set_manager_window_size(event.width, event.height)

    def exit_app(self, src_ignore=None, src2_ignore=None):
        self.emit("action-exit-app")

    def new_conn(self, src_ignore=None):
        self.emit("action-show-connect")

    def new_vm(self, src_ignore=None):
        self.emit("action-show-create", self.current_conn_uri())

    def show_about(self, src_ignore):
        self.emit("action-show-about")

    def show_preferences(self, src_ignore):
        self.emit("action-show-preferences")

    def show_host(self, src_ignore):
        uri = self.current_conn_uri(default_selection=True)
        self.emit("action-show-host", uri)

    def show_vm(self, ignore, ignore2=None, ignore3=None):
        conn = self.current_conn()
        vm = self.current_vm()
        if conn is None:
            return

        if vm:
            self.emit("action-show-vm", conn.get_uri(), vm.get_uuid())
        else:
            if not self.open_conn():
                self.emit("action-show-host", conn.get_uri())

    def open_clone_window(self, ignore1=None, ignore2=None, ignore3=None):
        if self.current_vmuuid():
            self.emit("action-clone-domain", self.current_conn_uri(),
                      self.current_vmuuid())

    def do_delete(self, ignore=None):
        conn = self.current_conn()
        vm = self.current_vm()
        if vm is None:
            self._do_delete_conn(conn)
        else:
            self.emit("action-delete-domain", conn.get_uri(), vm.get_uuid())

    def _do_delete_conn(self, conn):
        if conn is None:
            return

        result = self.err.yes_no(_("This will remove the connection:\n\n%s\n\n"
                                   "Are you sure?") % conn.get_uri())
        if not result:
            return

        self.emit("remove-conn", conn.get_uri())

    def set_pause_state(self, state):
        src = self.widget("vm-pause")
        try:
            self.ignore_pause = True
            src.set_active(state)
        finally:
            self.ignore_pause = False

    def pause_vm_button(self, src):
        if self.ignore_pause:
            return

        do_pause = src.get_active()

        # Set button state back to original value: just let the status
        # update function fix things for us
        self.set_pause_state(not do_pause)

        if do_pause:
            self.pause_vm(None)
        else:
            self.resume_vm(None)

    def start_vm(self, ignore):
        vm = self.current_vm()
        if vm is not None:
            self.emit("action-run-domain",
                      vm.conn.get_uri(), vm.get_uuid())

    def reboot_vm(self, ignore):
        vm = self.current_vm()
        if vm is not None:
            self.emit("action-reboot-domain",
                      vm.conn.get_uri(), vm.get_uuid())

    def poweroff_vm(self, ignore):
        vm = self.current_vm()
        if vm is not None:
            self.emit("action-shutdown-domain",
                      vm.conn.get_uri(), vm.get_uuid())

    def destroy_vm(self, ignore):
        vm = self.current_vm()
        if vm is not None:
            self.emit("action-destroy-domain",
                      vm.conn.get_uri(), vm.get_uuid())

    def reset_vm(self, ignore):
        vm = self.current_vm()
        if vm is not None:
            self.emit("action-reset-domain",
                      vm.conn.get_uri(), vm.get_uuid())

    def save_vm(self, ignore):
        vm = self.current_vm()
        if vm is not None:
            self.emit("action-save-domain",
                      vm.conn.get_uri(), vm.get_uuid())

    def pause_vm(self, ignore):
        vm = self.current_vm()
        if vm is not None:
            self.emit("action-suspend-domain",
                      vm.conn.get_uri(), vm.get_uuid())

    def resume_vm(self, ignore):
        vm = self.current_vm()
        if vm is not None:
            self.emit("action-resume-domain",
                      vm.conn.get_uri(), vm.get_uuid())

    def migrate_vm(self, ignore):
        vm = self.current_vm()
        if vm is not None:
            self.emit("action-migrate-domain",
                      vm.conn.get_uri(), vm.get_uuid())

    def close_conn(self, ignore):
        conn = self.current_conn()
        if conn.get_state() != vmmConnection.STATE_DISCONNECTED:
            conn.close()

    def open_conn(self, ignore=None):
        conn = self.current_conn()
        if conn.get_state() == vmmConnection.STATE_DISCONNECTED:
            conn.open()
            return True

    def _connect_error(self, conn, errmsg, tb, warnconsole):
        errmsg = errmsg.strip(" \n")
        tb = tb.strip(" \n")
        hint = ""
        show_errmsg = True

        if conn.is_remote():
            logging.debug(conn.get_transport())
            if re.search(r"nc: .* -- 'U'", tb):
                hint += _("The remote host requires a version of netcat/nc\n"
                          "which supports the -U option.")
                show_errmsg = False
            elif (conn.get_transport()[0] == "ssh" and
                  re.search(r"ssh-askpass", tb)):

                if self.config.askpass_package:
                    ret = packageutils.check_packagekit(
                                            self.err,
                                            self.config.askpass_package,
                                            False)
                    if ret:
                        conn.open()
                        return

                hint += _("You need to install openssh-askpass or "
                          "similar\nto connect to this host.")
                show_errmsg = False
            else:
                hint += _("Verify that the 'libvirtd' daemon is running\n"
                          "on the remote host.")

        elif conn.is_xen():
            hint += _("Verify that:\n"
                      " - A Xen host kernel was booted\n"
                      " - The Xen service has been started")

        else:
            if warnconsole:
                hint += _("Could not detect a local session: if you are \n"
                          "running virt-manager over ssh -X or VNC, you \n"
                          "may not be able to connect to libvirt as a \n"
                          "regular user. Try running as root.")
                show_errmsg = False
            elif re.search(r"libvirt-sock", tb):
                hint += _("Verify that the 'libvirtd' daemon is running.")
                show_errmsg = False

        msg = _("Unable to connect to libvirt.")
        if show_errmsg:
            msg += "\n\n%s" % errmsg
        if hint:
            msg += "\n\n%s" % hint

        msg = msg.strip("\n")
        details = msg
        details += "\n\n"
        details += "Libvirt URI is: %s\n\n" % conn.get_uri()
        details += tb

        self.err.show_err(msg, details, title=_("Virtual Machine Manager Connection Failure"))


    ####################################
    # VM add/remove management methods #
    ####################################

    def vm_row_key(self, vm):
        return vm.get_uuid() + ":" + vm.conn.get_uri()

    def vm_added(self, conn, vmuuid):
        vm = conn.get_vm(vmuuid)
        vm.connect("status-changed", self.vm_status_changed)
        vm.connect("resources-sampled", self.vm_resources_sampled)
        vm.connect("config-changed", self.vm_resources_sampled, True)
        vm.connect("inspection-changed", self.vm_inspection_changed)

        vmlist = self.widget("vm-list")
        model = vmlist.get_model()

        self._append_vm(model, vm, conn)

    def vm_removed(self, conn, vmuuid):
        vmlist = self.widget("vm-list")
        model = vmlist.get_model()

        parent = self.rows[conn.get_uri()].iter
        for row in range(model.iter_n_children(parent)):
            vm = model.get_value(model.iter_nth_child(parent, row), ROW_HANDLE)
            if vm.get_uuid() == vmuuid:
                model.remove(model.iter_nth_child(parent, row))
                del self.rows[self.vm_row_key(vm)]
                break

    def _build_conn_hint(self, conn):
        hint = conn.get_uri()
        if conn.state == conn.STATE_DISCONNECTED:
            hint += " (%s)" % _("Double click to connect")
        return hint

    def _build_conn_markup(self, conn, row):
        name = util.xml_escape(row[ROW_NAME])
        text = name
        if conn.state == conn.STATE_DISCONNECTED:
            text += " - " + _("Not Connected")
        elif conn.state == conn.STATE_CONNECTING:
            text += " - " + _("Connecting...")

        markup = "<span size='smaller'>%s</span>" % text
        return markup

    def _build_conn_color(self, conn):
        color = "#000000"
        if conn.state == conn.STATE_DISCONNECTED:
            color = "#5b5b5b"
        return color

    def _build_vm_markup(self, row):
        domtext     = ("<span size='smaller' weight='bold'>%s</span>" %
                       util.xml_escape(row[ROW_NAME]))
        statetext   = "<span size='smaller'>%s</span>" % row[ROW_STATUS]
        return domtext + "\n" + statetext

    def _build_vm_row(self, vm):
        row = []

        row.insert(ROW_HANDLE, vm)
        row.insert(ROW_NAME, vm.get_name())
        row.insert(ROW_MARKUP, "")
        row.insert(ROW_STATUS, vm.run_status())
        row.insert(ROW_STATUS_ICON, vm.run_status_icon_name())
        row.insert(ROW_KEY, vm.get_uuid())
        row.insert(ROW_HINT, util.xml_escape(vm.get_description()))
        row.insert(ROW_IS_CONN, False)
        row.insert(ROW_IS_CONN_CONNECTED, True)
        row.insert(ROW_IS_VM, True)
        row.insert(ROW_IS_VM_RUNNING, vm.is_active())
        row.insert(ROW_COLOR, None)
        row.insert(ROW_INSPECTION_OS_ICON,
                   self.get_inspection_icon_pixbuf(vm, 16, 16))

        row[ROW_MARKUP] = self._build_vm_markup(row)

        return row

    def _append_vm(self, model, vm, conn):
        row_key = self.vm_row_key(vm)
        if row_key in self.rows:
            return

        row = self._build_vm_row(vm)
        parent = self.rows[conn.get_uri()].iter

        _iter = model.append(parent, row)
        path = model.get_path(_iter)
        self.rows[row_key] = model[path]

        # Expand a connection when adding a vm to it
        self.widget("vm-list").expand_row(model.get_path(parent), False)

    def _build_conn_row(self, conn):
        row = []
        row.insert(ROW_HANDLE, conn)
        row.insert(ROW_NAME, conn.get_pretty_desc_inactive(False))
        row.insert(ROW_MARKUP, self._build_conn_markup(conn, row))
        row.insert(ROW_STATUS, ("<span size='smaller'>%s</span>" %
                                conn.get_state_text()))
        row.insert(ROW_STATUS_ICON, None)
        row.insert(ROW_KEY, conn.get_uri())
        row.insert(ROW_HINT, self._build_conn_hint(conn))
        row.insert(ROW_IS_CONN, True)
        row.insert(ROW_IS_CONN_CONNECTED,
                   conn.state != conn.STATE_DISCONNECTED)
        row.insert(ROW_IS_VM, False)
        row.insert(ROW_IS_VM_RUNNING, False)
        row.insert(ROW_COLOR, self._build_conn_color(conn))
        row.insert(ROW_INSPECTION_OS_ICON, None)

        return row

    def _append_conn(self, model, conn):
        row = self._build_conn_row(conn)

        _iter = model.append(None, row)
        path = model.get_path(_iter)
        self.rows[conn.get_uri()] = model[path]
        return _iter

    def add_conn(self, engine_ignore, conn):
        # Make sure error page isn't showing
        self.widget("vm-notebook").set_current_page(0)

        if conn.get_uri() in self.rows:
            return

        conn.connect("vm-added", self.vm_added)
        conn.connect("vm-removed", self.vm_removed)
        conn.connect("resources-sampled", self.conn_resources_sampled)
        conn.connect("state-changed", self.conn_state_changed)
        conn.connect("connect-error", self._connect_error)

        # add the connection to the treeModel
        vmlist = self.widget("vm-list")
        row = self._append_conn(vmlist.get_model(), conn)
        vmlist.get_selection().select_iter(row)

        # Try to make sure that 2 row descriptions don't collide
        connrows = []
        descs = []
        for row in self.rows.values():
            if row[ROW_IS_CONN]:
                connrows.append(row)
        for row in connrows:
            descs.append(row[ROW_NAME])

        for row in connrows:
            conn = row[ROW_HANDLE]
            name = row[ROW_NAME]
            if descs.count(name) <= 1:
                continue

            newname = conn.get_pretty_desc_inactive(False, True)
            self.conn_resources_sampled(conn, newname)

    def remove_conn(self, engine_ignore, uri):
        model = self.widget("vm-list").get_model()
        parent = self.rows[uri].iter

        if parent is None:
            return

        child = model.iter_children(parent)
        while child is not None:
            del self.rows[self.vm_row_key(model.get_value(child, ROW_HANDLE))]
            model.remove(child)
            child = model.iter_children(parent)
        model.remove(parent)

        del self.rows[uri]


    #############################
    # State/UI updating methods #
    #############################

    def vm_status_changed(self, vm, oldstatus, newstatus):
        ignore = newstatus
        ignore = oldstatus
        parent = self.rows[vm.conn.get_uri()].iter
        vmlist = self.widget("vm-list")
        model = vmlist.get_model()

        missing = True
        for row in range(model.iter_n_children(parent)):
            _iter = model.iter_nth_child(parent, row)
            if model.get_value(_iter, ROW_KEY) == vm.get_uuid():
                missing = False
                break

        if missing:
            self._append_vm(model, vm, vm.conn)

        # Update run/shutdown/pause button states
        self.vm_selected()
        self.vm_resources_sampled(vm)

    def vm_resources_sampled(self, vm, config_changed=False):
        vmlist = self.widget("vm-list")
        model = vmlist.get_model()

        if self.vm_row_key(vm) not in self.rows:
            return

        row = self.rows[self.vm_row_key(vm)]
        row[ROW_NAME] = vm.get_name()
        row[ROW_STATUS] = vm.run_status()
        row[ROW_STATUS_ICON] = vm.run_status_icon_name()
        row[ROW_IS_VM_RUNNING] = vm.is_active()
        row[ROW_MARKUP] = self._build_vm_markup(row)

        if config_changed:
            desc = vm.get_description()
            if not can_set_row_none:
                desc = desc or ""
            row[ROW_HINT] = util.xml_escape(desc)

        model.row_changed(row.path, row.iter)

    def vm_inspection_changed(self, vm):
        vmlist = self.widget("vm-list")
        model = vmlist.get_model()

        if self.vm_row_key(vm) not in self.rows:
            return

        row = self.rows[self.vm_row_key(vm)]
        row[ROW_INSPECTION_OS_ICON] = \
            self.get_inspection_icon_pixbuf(vm, 16, 16)
        model.row_changed(row.path, row.iter)

    def get_inspection_icon_pixbuf(self, vm, w, h):
        # libguestfs gives us the PNG data as a string.
        png_data = vm.inspection.icon
        if png_data is None:
            return None

        try:
            pb = GdkPixbuf.PixbufLoader()
            pb.set_size(w, h)
            pb.write(png_data)
            pb.close()
            return pb.get_pixbuf()
        except:
            logging.exception("Error loading inspection icon data")
            vm.inspection.icon = None
            return None

    def conn_state_changed(self, conn):
        self.conn_resources_sampled(conn)
        self.vm_selected()

    def conn_resources_sampled(self, conn, newname=None):
        vmlist = self.widget("vm-list")
        model = vmlist.get_model()
        row = self.rows[conn.get_uri()]

        if newname:
            row[ROW_NAME] = newname
        row[ROW_MARKUP] = self._build_conn_markup(conn, row)
        row[ROW_STATUS] = ("<span size='smaller'>%s</span>" %
                           conn.get_state_text())
        row[ROW_IS_CONN_CONNECTED] = conn.state != conn.STATE_DISCONNECTED
        row[ROW_COLOR] = self._build_conn_color(conn)
        row[ROW_HINT] = self._build_conn_hint(conn)

        if conn.get_state() in [vmmConnection.STATE_DISCONNECTED,
                                vmmConnection.STATE_CONNECTING]:
            # Connection went inactive, delete any VM child nodes
            parent = self.rows[conn.get_uri()].iter
            if parent is not None:
                child = model.iter_children(parent)
                while child is not None:
                    del self.rows[self.vm_row_key(model.get_value(child,
                                                                  ROW_HANDLE))]
                    model.remove(child)
                    child = model.iter_children(parent)

        self.max_disk_rate = max(self.max_disk_rate, conn.disk_io_max_rate())
        self.max_net_rate = max(self.max_net_rate,
                                conn.network_traffic_max_rate())

        model.row_changed(row.path, row.iter)

    def change_run_text(self, can_restore):
        if can_restore:
            text = _("_Restore")
        else:
            text = _("_Run")
        strip_text = text.replace("_", "")

        self.vmmenu_items["run"].get_child().set_label(text)
        self.widget("vm-run").set_label(strip_text)

    def vm_selected(self, ignore=None):
        vm = self.current_vm()

        show_open = bool(vm)
        show_details = bool(vm)
        host_details = bool(len(self.rows))

        show_run = bool(vm and vm.is_runable())
        is_paused = bool(vm and vm.is_paused())
        if is_paused:
            show_pause = bool(vm and vm.is_unpauseable())
        else:
            show_pause = bool(vm and vm.is_pauseable())
        show_shutdown = bool(vm and vm.is_stoppable())

        if vm and vm.managedsave_supported:
            self.change_run_text(vm.hasSavedImage())

        self.widget("vm-open").set_sensitive(show_open)
        self.widget("vm-run").set_sensitive(show_run)
        self.widget("vm-shutdown").set_sensitive(show_shutdown)
        self.set_pause_state(is_paused)
        self.widget("vm-pause").set_sensitive(show_pause)

        self.widget("menu_edit_details").set_sensitive(show_details)
        self.widget("menu_host_details").set_sensitive(host_details)

    def popup_vm_menu_key(self, widget_ignore, event):
        if Gdk.keyval_name(event.keyval) != "Menu":
            return False

        vmlist = self.widget("vm-list")
        treeselection = vmlist.get_selection()
        model, _iter = treeselection.get_selected()
        self.popup_vm_menu(model, _iter, event)
        return True

    def popup_vm_menu_button(self, widget, event):
        if event.button != 3:
            return False

        tup = widget.get_path_at_pos(int(event.x), int(event.y))
        if tup is None:
            return False
        path = tup[0]
        model = widget.get_model()
        _iter = model.get_iter(path)

        self.popup_vm_menu(model, _iter, event)
        return False

    def popup_vm_menu(self, model, _iter, event):
        if model.iter_parent(_iter) is not None:
            # Popup the vm menu
            vm = model.get_value(_iter, ROW_HANDLE)

            destroy = vm.is_destroyable()
            run     = vm.is_runable()
            stop    = vm.is_stoppable()
            paused  = vm.is_paused()
            ro      = vm.is_read_only()

            self.vmmenu_items["run"].set_sensitive(run)
            self.vmmenu_items["shutdown"].set_sensitive(stop)
            self.vmmenu_items["pause"].set_property("visible", not paused)
            self.vmmenu_items["pause"].set_sensitive(stop)
            self.vmmenu_items["resume"].set_property("visible", paused)
            self.vmmenu_items["resume"].set_sensitive(paused)
            self.vmmenu_items["migrate"].set_sensitive(stop)
            self.vmmenu_items["clone"].set_sensitive(not ro)

            self.vmmenushutdown_items["poweroff"].set_sensitive(stop)
            self.vmmenushutdown_items["reboot"].set_sensitive(stop)
            self.vmmenushutdown_items["forcepoweroff"].set_sensitive(destroy)
            self.vmmenushutdown_items["save"].set_sensitive(destroy)
            self.vmmenu.popup(None, None, None, None, 0, event.time)
        else:
            # Pop up connection menu
            conn = model.get_value(_iter, ROW_HANDLE)
            disconn = (conn.get_state() == vmmConnection.STATE_DISCONNECTED)
            conning = (conn.get_state() == vmmConnection.STATE_CONNECTING)

            self.connmenu_items["create"].set_sensitive(not disconn)
            self.connmenu_items["disconnect"].set_sensitive(not (disconn or
                                                                 conning))
            self.connmenu_items["connect"].set_sensitive(disconn)
            self.connmenu_items["delete"].set_sensitive(disconn)

            self.connmenu.popup(None, None, None, None, 0, event.time)


    #################
    # Stats methods #
    #################

    def vmlist_name_sorter(self, model, iter1, iter2, ignore):
        return cmp(model.get_value(iter1, ROW_NAME),
                   model.get_value(iter2, ROW_NAME))

    def vmlist_guest_cpu_usage_sorter(self, model, iter1, iter2, ignore):
        obj1 = model.get_value(iter1, ROW_HANDLE)
        obj2 = model.get_value(iter2, ROW_HANDLE)

        return cmp(obj1.guest_cpu_time_percentage(),
                   obj2.guest_cpu_time_percentage())

    def vmlist_host_cpu_usage_sorter(self, model, iter1, iter2, ignore):
        obj1 = model.get_value(iter1, ROW_HANDLE)
        obj2 = model.get_value(iter2, ROW_HANDLE)

        return cmp(obj1.host_cpu_time_percentage(),
                   obj2.host_cpu_time_percentage())

    def vmlist_disk_io_sorter(self, model, iter1, iter2, ignore):
        obj1 = model.get_value(iter1, ROW_HANDLE)
        obj2 = model.get_value(iter2, ROW_HANDLE)

        return cmp(obj1.disk_io_rate(), obj2.disk_io_rate())

    def vmlist_network_usage_sorter(self, model, iter1, iter2, ignore):
        obj1 = model.get_value(iter1, ROW_HANDLE)
        obj2 = model.get_value(iter2, ROW_HANDLE)

        return cmp(obj1.network_traffic_rate(), obj2.network_traffic_rate())

    def enable_polling(self, column):
        if column == COL_DISK:
            widgn = "menu_view_stats_disk"
            do_enable = self.config.get_stats_enable_disk_poll()
        elif column == COL_NETWORK:
            widgn = "menu_view_stats_network"
            do_enable = self.config.get_stats_enable_net_poll()
        widget = self.widget(widgn)

        tool_text = ""

        if do_enable:
            widget.set_sensitive(True)
        else:
            if widget.get_active():
                widget.set_active(False)
            widget.set_sensitive(False)
            tool_text = _("Disabled in preferences dialog.")

        widget.set_tooltip_text(tool_text)

        disabled_text = _(" (disabled)")
        current_text = widget.get_label().strip(disabled_text)
        if tool_text:
            current_text = current_text + disabled_text
        widget.set_label(current_text)

    def toggle_network_traffic_visible_widget(self):
        val = self.config.is_vmlist_network_traffic_visible()
        self.netcol.set_visible(val)
        self.widget("menu_view_stats_network").set_active(val)

    def toggle_disk_io_visible_widget(self):
        val = self.config.is_vmlist_disk_io_visible()
        self.diskcol.set_visible(val)
        self.widget("menu_view_stats_disk").set_active(val)

    def toggle_guest_cpu_usage_visible_widget(self):
        val = self.config.is_vmlist_guest_cpu_usage_visible()
        self.guestcpucol.set_visible(val)
        self.widget("menu_view_stats_guest_cpu").set_active(val)

    def toggle_host_cpu_usage_visible_widget(self):
        val = self.config.is_vmlist_host_cpu_usage_visible()
        self.hostcpucol.set_visible(val)
        self.widget("menu_view_stats_host_cpu").set_active(val)

    def toggle_stats_visible(self, src, stats_id):
        visible = src.get_active()
        set_stats = {
            COL_GUEST_CPU: self.config.set_vmlist_guest_cpu_usage_visible,
            COL_HOST_CPU: self.config.set_vmlist_host_cpu_usage_visible,
            COL_DISK: self.config.set_vmlist_disk_io_visible,
            COL_NETWORK: self.config.set_vmlist_network_traffic_visible,
        }
        set_stats[stats_id](visible)

    def toggle_stats_visible_guest_cpu(self, src):
        self.toggle_stats_visible(src, COL_GUEST_CPU)
    def toggle_stats_visible_host_cpu(self, src):
        self.toggle_stats_visible(src, COL_HOST_CPU)
    def toggle_stats_visible_disk(self, src):
        self.toggle_stats_visible(src, COL_DISK)
    def toggle_stats_visible_network(self, src):
        self.toggle_stats_visible(src, COL_NETWORK)

    def guest_cpu_usage_img(self, column_ignore, cell, model, _iter, data):
        obj = model.get_value(_iter, ROW_HANDLE)
        if obj is None or not hasattr(obj, "conn"):
            return

        data = obj.guest_cpu_time_vector_limit(GRAPH_LEN)
        cell.set_property('data_array', data)

    def host_cpu_usage_img(self, column_ignore, cell, model, _iter, data):
        obj = model.get_value(_iter, ROW_HANDLE)
        if obj is None or not hasattr(obj, "conn"):
            return

        data = obj.host_cpu_time_vector_limit(GRAPH_LEN)
        cell.set_property('data_array', data)

    def disk_io_img(self, column_ignore, cell, model, _iter, data):
        obj = model.get_value(_iter, ROW_HANDLE)
        if obj is None or not hasattr(obj, "conn"):
            return

        data = obj.disk_io_vector_limit(GRAPH_LEN, self.max_disk_rate)
        cell.set_property('data_array', data)

    def network_traffic_img(self, column_ignore, cell, model, _iter, data):
        obj = model.get_value(_iter, ROW_HANDLE)
        if obj is None or not hasattr(obj, "conn"):
            return

        data = obj.network_traffic_vector_limit(GRAPH_LEN, self.max_net_rate)
        cell.set_property('data_array', data)

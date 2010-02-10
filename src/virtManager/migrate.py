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

import gobject
import gtk.glade

import traceback
import logging

import virtinst
import libvirt

from virtManager import util
from virtManager.error import vmmErrorDialog
from virtManager.asyncjob import vmmAsyncJob
from virtManager.createmeter import vmmCreateMeter
from virtManager.domain import vmmDomain

def uri_join(uri_tuple):
    scheme, user, host, path, query, fragment = uri_tuple

    user = (user and (user + "@") or "")
    host = host or ""
    path = path or "/"
    query = (query and ("?" + query) or "")
    fragment = (fragment and ("#" + fragment) or "")

    return "%s://%s%s%s%s%s" % (scheme, user, host, path, fragment, query)


class vmmMigrateDialog(gobject.GObject):
    __gsignals__ = {
    }

    def __init__(self, config, vm, engine):
        self.__gobject_init__()
        self.window = gtk.glade.XML(config.get_glade_dir() + \
                                    "/vmm-migrate.glade",
                                    "vmm-migrate", domain="virt-manager")
        self.config = config
        self.vm = vm
        self.conn = vm.connection
        self.engine = engine

        self.topwin = self.window.get_widget("vmm-migrate")
        self.err = vmmErrorDialog(self.topwin,
                                  0, gtk.MESSAGE_ERROR, gtk.BUTTONS_CLOSE,
                                  _("Unexpected Error"),
                                  _("An unexpected error occurred"))
        self.topwin.hide()

        self.destconn_rows = []

        self.window.signal_autoconnect({
            "on_vmm_migrate_delete_event" : self.close,

            "on_migrate_cancel_clicked" : self.close,
            "on_migrate_finish_clicked" : self.finish,

            "on_migrate_dest_changed" : self.destconn_changed,
            "on_migrate_set_rate_toggled" : self.toggle_set_rate,
            "on_migrate_set_interface_toggled" : self.toggle_set_interface,
            "on_migrate_set_port_toggled" : self.toggle_set_port,
        })
        util.bind_escape_key_close(self)

        blue = gtk.gdk.color_parse("#0072A8")
        self.window.get_widget("migrate-header").modify_bg(gtk.STATE_NORMAL,
                                                           blue)
        image = gtk.image_new_from_icon_name("vm_clone_wizard",
                                             gtk.ICON_SIZE_DIALOG)
        image.show()
        self.window.get_widget("migrate-vm-icon-box").pack_end(image, False)

        self.init_state()

    def show(self):
        self.reset_state()
        self.topwin.show()
        self.topwin.present()

    def close(self, ignore1=None, ignore2=None):
        self.topwin.hide()
        return 1

    def init_state(self):
        # [hostname, conn, can_migrate, tooltip]
        dest_model = gtk.ListStore(str, object, bool, str)
        dest_combo = self.window.get_widget("migrate-dest")
        dest_combo.set_model(dest_model)
        text = gtk.CellRendererText()
        dest_combo.pack_start(text, True)
        dest_combo.add_attribute(text, 'text', 0)
        dest_combo.add_attribute(text, 'sensitive', 2)
        dest_model.set_sort_column_id(0, gtk.SORT_ASCENDING)
        # XXX no way to set tooltips here, kind of annoying

        # Hook up signals to get connection listing
        self.engine.connect("connection-added", self.dest_add_connection)
        self.engine.connect("connection-removed", self.dest_remove_connection)
        self.destconn_changed(dest_combo)

    def reset_state(self):
        title_str = ("<span size='large' color='white'>%s '%s'</span>" %
                     (_("Migrate"), self.vm.get_name()))
        self.window.get_widget("migrate-main-label").set_markup(title_str)

        self.window.get_widget("migrate-cancel").grab_focus()

        name = self.vm.get_name()
        srchost = self.conn.get_hostname()

        self.window.get_widget("migrate-label-name").set_text(name)
        self.window.get_widget("migrate-label-src").set_text(srchost)

        self.window.get_widget("migrate-advanced-expander").set_expanded(False)
        self.window.get_widget("migrate-set-interface").set_active(False)
        self.window.get_widget("migrate-set-rate").set_active(False)
        self.window.get_widget("migrate-set-port").set_active(False)

        running = self.vm.is_active()
        self.window.get_widget("migrate-offline").set_active(not running)
        self.window.get_widget("migrate-offline").set_sensitive(running)

        self.window.get_widget("migrate-rate").set_value(0)
        self.window.get_widget("migrate-secure").set_active(False)

        if self.conn.is_xen():
            # Default xen port is 8002
            self.window.get_widget("migrate-port").set_value(8002)
        else:
            # QEMU migrate port range is 49152+64
            self.window.get_widget("migrate-port").set_value(49152)

        secure_box = self.window.get_widget("migrate-secure-box")
        support_secure = hasattr(libvirt, "VIR_MIGRATE_TUNNELLED")
        secure_tooltip = ""
        if not support_secure:
            secure_tooltip = _("Libvirt version does not support tunnelled "
                               "migration.")

        secure_box.set_sensitive(support_secure)
        util.tooltip_wrapper(secure_box, secure_tooltip)

        self.rebuild_dest_rows()

    def set_state(self, vm):
        self.vm = vm
        self.conn = vm.connection
        self.reset_state()

    def destconn_changed(self, src):
        active = src.get_active()
        tooltip = None
        if active == -1:
            tooltip = _("A valid destination connection must be selected.")

        self.window.get_widget("migrate-finish").set_sensitive(active != -1)
        util.tooltip_wrapper(self.window.get_widget("migrate-finish"), tooltip)

    def toggle_set_rate(self, src):
        enable = src.get_active()
        self.window.get_widget("migrate-rate").set_sensitive(enable)

    def toggle_set_interface(self, src):
        enable = src.get_active()
        port_enable = self.window.get_widget("migrate-set-port").get_active()
        self.window.get_widget("migrate-interface").set_sensitive(enable)
        self.window.get_widget("migrate-set-port").set_sensitive(enable)
        self.window.get_widget("migrate-port").set_sensitive(enable and
                                                             port_enable)

    def toggle_set_port(self, src):
        enable = src.get_active()
        self.window.get_widget("migrate-port").set_sensitive(enable)

    def get_config_destconn(self):
        combo = self.window.get_widget("migrate-dest")
        model = combo.get_model()

        idx = combo.get_active()
        if idx == -1:
            return None

        row = model[idx]
        if not row[2]:
            return None

        return row[1]

    def get_config_offline(self):
        return self.window.get_widget("migrate-offline").get_active()
    def get_config_secure(self):
        return self.window.get_widget("migrate-secure").get_active()

    def get_config_rate_enabled(self):
        return self.window.get_widget("migrate-rate").get_property("sensitive")
    def get_config_rate(self):
        if not self.get_config_rate_enabled():
            return 0
        return int(self.window.get_widget("migrate-rate").get_value())

    def get_config_interface_enabled(self):
        return self.window.get_widget("migrate-interface").get_property("sensitive")
    def get_config_interface(self):
        if not self.get_config_interface_enabled():
            return None
        return self.window.get_widget("migrate-interface").get_text()

    def get_config_port_enabled(self):
        return self.window.get_widget("migrate-port").get_property("sensitive")
    def get_config_port(self):
        if not self.get_config_port_enabled():
            return 0
        return int(self.window.get_widget("migrate-port").get_value())

    def build_localhost_uri(self, destconn):
        desthost = destconn.get_qualified_hostname()
        if desthost == "localhost":
            # We couldn't find a host name for the destination machine
            # that is accessible from the source machine.
            # /etc/hosts is likely borked and the only hostname it will
            # give us is localhost. Remember, the dest machine can actually
            # be our local machine so we may not already know its hostname
            raise RuntimeError(_("Could not determine remotely accessible "
                                 "hostname for destination connection."))

        desturi_tuple = virtinst.util.uri_split(destconn.get_uri())

        # Replace dest hostname with src hostname
        desturi_tuple = list(desturi_tuple)
        desturi_tuple[2] = desthost
        return uri_join(desturi_tuple)

    def build_migrate_uri(self, destconn):
        conn = self.conn

        interface = self.get_config_interface()
        port = self.get_config_port()
        secure = self.get_config_secure()

        if not interface:
            if not secure:
                return None

            # For secure migration, we need to make sure we aren't migrating
            # to the local connection, because libvirt will pull try to use
            # 'qemu:///system' as the migrate URI which will deadlock
            if destconn.is_local():
                return self.build_localhost_uri(destconn)

        uri = ""
        if conn.is_xen():
            uri = "xenmigr://%s" % interface

        else:
            uri = "tcp:%s" % interface

        if port:
            uri += ":%s" % port

        return uri

    def rebuild_dest_rows(self):
        newrows = []

        for row in self.destconn_rows:
            newrows.append(self.build_dest_row(row[1]))

        self.destconn_rows = newrows
        self.populate_dest_combo()

    def populate_dest_combo(self):
        combo = self.window.get_widget("migrate-dest")
        model = combo.get_model()
        idx = combo.get_active()
        idxconn = None
        if idx != -1:
            idxconn = model[idx][1]

        rows = [[_("No connections available."), None, False, None]]
        if self.destconn_rows:
            rows = self.destconn_rows

        model.clear()
        for r in rows:
            # Don't list the current connection
            if r[1] == self.conn:
                continue
            model.append(r)

        # Find old index
        idx = -1
        for i in range(len(model)):
            row = model[i]
            conn = row[1]

            if idxconn:
                if conn == idxconn and row[2]:
                    idx = i
                    break
            else:
                if row[2]:
                    idx = i
                    break

        combo.set_active(idx)

    def dest_add_connection(self, engine_ignore, conn):
        combo = self.window.get_widget("migrate-dest")
        model = combo.get_model()

        newrow = self.build_dest_row(conn)

        # Make sure connection isn't already present
        for row in model:
            if row[1] and row[1].get_uri() == newrow[1].get_uri():
                return

        conn.connect("state-changed", self.destconn_state_changed)
        self.destconn_rows.append(newrow)
        self.populate_dest_combo()

    def dest_remove_connection(self, engine_ignore, conn):
        # Make sure connection isn't already present
        for row in self.destconn_rows:
            if row[1] and row[1].get_uri() == conn.get_uri():
                self.destconn_rows.remove(row)

        self.populate_dest_combo()

    def destconn_state_changed(self, conn):
        for row in self.destconn_rows:
            if row[1] == conn:
                self.destconn_rows.remove(row)
                self.destconn_rows.append(self.build_dest_row(conn))

        self.populate_dest_combo()

    def build_dest_row(self, destconn):
        driver = self.conn.get_driver()
        origuri = self.conn.get_uri()

        can_migrate = False
        desc = destconn.get_pretty_desc_inactive()
        reason = ""
        desturi = destconn.get_uri()

        if destconn.get_driver() != driver:
            reason = _("Connection hypervisors do not match.")
        elif destconn.get_state() == destconn.STATE_DISCONNECTED:
            reason = _("Connection is disconnected.")
        elif destconn.get_uri() == origuri:
            # Same connection
            pass
        elif destconn.get_state() == destconn.STATE_ACTIVE:
            # Assumably we can migrate to this connection
            can_migrate = True
            reason = desturi

        return [desc, destconn, can_migrate, reason]


    def validate(self):
        interface = self.get_config_interface()
        rate = self.get_config_rate()
        port = self.get_config_port()

        if self.get_config_interface_enabled() and interface == None:
            return self.err.val_err(_("An interface must be specified."))

        if self.get_config_rate_enabled() and rate == 0:
            return self.err.val_err(_("Transfer rate must be greater than 0."))

        if self.get_config_port_enabled() and port == 0:
            return self.err.val_err(_("Port must be greater than 0."))

        return True

    def finish(self, src):
        try:
            if not self.validate():
                return

            destconn = self.get_config_destconn()
            srchost = self.vm.get_connection().get_hostname()
            dsthost = destconn.get_qualified_hostname()
            live = not self.get_config_offline()
            secure = self.get_config_secure()
            uri = self.build_migrate_uri(destconn)
            rate = self.get_config_rate()
            if rate:
                rate = int(rate)
        except Exception, e:
            details = "".join(traceback.format_exc())
            self.err.show_err((_("Uncaught error validating input: %s") %
                               str(e)), details)
            return

        self.topwin.set_sensitive(False)
        self.topwin.window.set_cursor(gtk.gdk.Cursor(gtk.gdk.WATCH))

        progWin = vmmAsyncJob(self.config, self._async_migrate,
                              [self.vm, destconn, uri, rate, live, secure],
                              title=_("Migrating VM '%s'" % self.vm.get_name()),
                              text=(_("Migrating VM '%s' from %s to %s. "
                                      "This may take awhile.") %
                                      (self.vm.get_name(), srchost, dsthost)))
        progWin.run()
        error, details = progWin.get_error()

        if error:
            self.err.show_err(error, details)

        self.topwin.set_sensitive(True)
        self.topwin.window.set_cursor(gtk.gdk.Cursor(gtk.gdk.TOP_LEFT_ARROW))

        if error is None:
            self.conn.tick(noStatsUpdate=True)
            destconn.tick(noStatsUpdate=True)
            self.close()

    def _async_migrate(self, origvm, origdconn, migrate_uri, rate, live,
                       secure, asyncjob):
        errinfo = None
        try:
            try:
                ignore = vmmCreateMeter(asyncjob)

                srcconn = util.dup_conn(self.config, origvm.get_connection(),
                                        return_conn_class=True)
                dstconn = util.dup_conn(self.config, origdconn,
                                        return_conn_class=True)

                vminst = srcconn.vmm.lookupByName(origvm.get_name())
                vm = vmmDomain(self.config, srcconn, vminst, vminst.UUID())

                logging.debug("Migrating vm=%s from %s to %s", vm.get_name(),
                              srcconn.get_uri(), dstconn.get_uri())
                vm.migrate(dstconn, migrate_uri, rate, live, secure)
            except Exception, e:
                errinfo = (str(e), ("Unable to migrate guest:\n %s" %
                                    "".join(traceback.format_exc())))
        finally:
            if errinfo:
                asyncjob.set_error(errinfo[0], errinfo[1])


gobject.type_register(vmmMigrateDialog)
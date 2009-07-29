#
# Copyright (C) 2006 Red Hat, Inc.
# Copyright (C) 2006 Hugh O. Brock <hbrock@redhat.com>
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
import gtk.glade
import gobject
import logging

import virtinst

import virtManager.opticalhelper
from virtManager.storagebrowse import vmmStorageBrowser
from virtManager.error import vmmErrorDialog

class vmmChooseCD(gobject.GObject):
    __gsignals__ = {"cdrom-chosen": (gobject.SIGNAL_RUN_FIRST,
                           gobject.TYPE_NONE,
                           (str, str, str)), # type, source, target
}
    def __init__(self, config, dev_id_info, connection):
        self.__gobject_init__()
        self.window = gtk.glade.XML(config.get_glade_dir() + "/vmm-choose-cd.glade", "vmm-choose-cd", domain="virt-manager")
        self.err = vmmErrorDialog(self.window.get_widget("vmm-choose-cd"),
                                  0, gtk.MESSAGE_ERROR, gtk.BUTTONS_CLOSE,
                                  _("Unexpected Error"),
                                  _("An unexpected error occurred"))
        self.topwin = self.window.get_widget("vmm-choose-cd")
        self.topwin.hide()

        self.config = config
        self.dev_id_info = dev_id_info
        self.conn = connection
        self.storage_browser = None

        self.window.signal_autoconnect({
            "on_media_toggled": self.media_toggled,
            "on_fv_iso_location_browse_clicked": self.browse_fv_iso_location,
            "on_cd_path_changed": self.change_cd_path,
            "on_ok_clicked": self.ok,
            "on_vmm_choose_cd_delete_event": self.cancel,
            "on_cancel_clicked": self.cancel,
            })

        self.window.get_widget("iso-image").set_active(True)

        self.initialize_opt_media()
        self.reset_state()

    def close(self,ignore1=None,ignore2=None):
        self.window.get_widget("vmm-choose-cd").hide()
        return 1

    def cancel(self,ignore1=None,ignore2=None):
        self.window.get_widget("vmm-choose-cd").hide()

    def show(self):
        win = self.window.get_widget("vmm-choose-cd")
        self.reset_state()
        win.show()

    def reset_state(self):
        if self.conn.is_remote():
            self.window.get_widget("physical-media").set_sensitive(False)
            self.window.get_widget("iso-image").set_active(True)
            self.window.get_widget("cd-path").set_active(-1)
            self.window.get_widget("iso-file-chooser").set_sensitive(False)
        else:
            self.window.get_widget("physical-media").set_sensitive(True)
            self.window.get_widget("iso-file-chooser").set_sensitive(True)

    def ok(self,ignore1=None, ignore2=None):
        path = None

        if self.window.get_widget("iso-image").get_active():
            path = self.window.get_widget("iso-path").get_text()
        else:
            cd = self.window.get_widget("cd-path")
            idx = cd.get_active()
            model = cd.get_model()
            if idx != -1:
                path = model[idx][virtManager.opticalhelper.OPTICAL_PATH]

        if path == "" or path == None:
            return self.err.val_err(_("Invalid Media Path"),
                                    _("A media path must be specified."))

        try:
            dev=virtinst.VirtualDisk.DEVICE_CDROM
            disk = virtinst.VirtualDisk(path=path,
                                        device=dev,
                                        readOnly=True,
                                        conn=self.conn.vmm)
        except Exception, e:
            return self.err.val_err(_("Invalid Media Path"), str(e))

        self.emit("cdrom-chosen", disk.type, disk.path, self.dev_id_info)
        self.cancel()

    def media_toggled(self, ignore1=None, ignore2=None):
        if self.window.get_widget("physical-media").get_active():
            self.window.get_widget("cd-path").set_sensitive(True)
            self.window.get_widget("iso-path").set_sensitive(False)
            self.window.get_widget("iso-file-chooser").set_sensitive(False)
        else:
            self.window.get_widget("cd-path").set_sensitive(False)
            self.window.get_widget("iso-path").set_sensitive(True)
            self.window.get_widget("iso-file-chooser").set_sensitive(True)

    def change_cd_path(self, ignore1=None, ignore2=None):
        pass

    def browse_fv_iso_location(self, ignore1=None, ignore2=None):
        self._browse_file(_("Locate ISO Image"))

    def initialize_opt_media(self):
        try:
            widget = self.window.get_widget("cd-path")
            virtManager.opticalhelper.init_optical_combo(widget)
            self.window.get_widget("physical-media").set_sensitive(True)
        except Exception, e:
            logging.error("Unable to create optical-helper widget: '%s'", e)
            self.window.get_widget("physical-media").set_sensitive(False)

    def set_storage_path(self, src, path):
        self.window.get_widget("iso-path").set_text(path)

    def _browse_file(self, dialog_name):
        if self.storage_browser == None:
            self.storage_browser = vmmStorageBrowser(self.config, self.conn,
                                                     True)
            self.storage_browser.connect("storage-browse-finish",
                                         self.set_storage_path)
        self.storage_browser.local_args = { "dialog_name": dialog_name,
                                            "browse_reason":
                                                 self.config.CONFIG_DIR_MEDIA }
        self.storage_browser.show(self.conn)
        return None

gobject.type_register(vmmChooseCD)

#
# Copyright (C) 2006 Red Hat, Inc.
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

import gtk.glade
import gobject

PREFS_PAGE_STATS    = 0
PREFS_PAGE_VM_PREFS = 1

class vmmPreferences(gobject.GObject):
    __gsignals__ = {
        "action-show-help": (gobject.SIGNAL_RUN_FIRST,
                             gobject.TYPE_NONE, [str]),
        }
    def __init__(self, config):
        self.__gobject_init__()
        self.window = gtk.glade.XML(config.get_glade_dir() + "/vmm-preferences.glade", "vmm-preferences", domain="virt-manager")
        self.config = config

        self.topwin = self.window.get_widget("vmm-preferences")
        self.topwin.hide()

        self.config.on_console_popup_changed(self.refresh_console_popup)
        self.config.on_console_keygrab_changed(self.refresh_console_keygrab)
        self.config.on_stats_update_interval_changed(self.refresh_update_interval)
        self.config.on_stats_history_length_changed(self.refresh_history_length)

        self.config.on_stats_enable_disk_poll_changed(self.refresh_disk_poll)
        self.config.on_stats_enable_net_poll_changed(self.refresh_net_poll)
        self.config.on_stats_enable_mem_poll_changed(self.refresh_mem_poll)
        self.config.on_stats_enable_cpu_poll_changed(self.refresh_cpu_poll)

        self.refresh_update_interval()
        self.refresh_history_length()
        self.refresh_console_popup()
        self.refresh_console_keygrab()
        self.refresh_sound_options()
        self.refresh_disk_poll()
        self.refresh_net_poll()
        self.refresh_mem_poll()
        self.refresh_cpu_poll()

        self.window.signal_autoconnect({
            "on_prefs_stats_update_interval_changed": self.change_update_interval,
            "on_prefs_stats_history_length_changed": self.change_history_length,
            "on_prefs_console_popup_changed": self.change_console_popup,
            "on_prefs_console_keygrab_changed": self.change_console_keygrab,
            "on_prefs_close_clicked": self.close,
            "on_vmm_preferences_delete_event": self.close,
            "on_prefs_help_clicked": self.show_help,
            "on_prefs_sound_local_toggled": self.change_local_sound,
            "on_prefs_sound_remote_toggled": self.change_remote_sound,
            "on_prefs_stats_enable_disk_toggled": self.change_disk_poll,
            "on_prefs_stats_enable_net_toggled": self.change_net_poll,
            "on_prefs_stats_enable_mem_toggled": self.change_mem_poll,
            "on_prefs_stats_enable_cpu_toggled": self.change_cpu_poll,
            })

    def close(self, ignore1=None, ignore2=None):
        self.topwin.hide()
        return 1

    def show(self):
        self.topwin.show()
        self.topwin.present()

    #########################
    # Config Change Options #
    #########################

    def refresh_update_interval(self, ignore1=None,ignore2=None,ignore3=None,ignore4=None):
        self.window.get_widget("prefs-stats-update-interval").set_value(self.config.get_stats_update_interval())

    def refresh_history_length(self, ignore1=None,ignore2=None,ignore3=None,ignore4=None):
        self.window.get_widget("prefs-stats-history-len").set_value(self.config.get_stats_history_length())

    def refresh_console_popup(self,ignore1=None,ignore2=None,ignore3=None,ignore4=None):
        self.window.get_widget("prefs-console-popup").set_active(self.config.get_console_popup())

    def refresh_console_keygrab(self,ignore1=None,ignore2=None,ignore3=None,ignore4=None):
        self.window.get_widget("prefs-console-keygrab").set_active(self.config.get_console_keygrab())

    def refresh_sound_options(self, ignore1=None, ignore2=None, ignore=None,
                              ignore4=None):
        self.window.get_widget("prefs-sound-local").set_active(self.config.get_local_sound())
        self.window.get_widget("prefs-sound-remote").set_active(self.config.get_remote_sound())

    def refresh_disk_poll(self, ignore1=None, ignore2=None, ignore3=None,
                          ignore4=None):
        self.window.get_widget("prefs-stats-enable-disk").set_active(self.config.get_stats_enable_disk_poll())
    def refresh_net_poll(self, ignore1=None, ignore2=None, ignore3=None,
                         ignore4=None):
        self.window.get_widget("prefs-stats-enable-net").set_active(self.config.get_stats_enable_net_poll())
    def refresh_mem_poll(self, ignore1=None, ignore2=None, ignore3=None,
                         ignore4=None):
        self.window.get_widget("prefs-stats-enable-mem").set_active(self.config.get_stats_enable_mem_poll())
    def refresh_cpu_poll(self, ignore1=None, ignore2=None, ignore3=None,
                         ignore4=None):
        self.window.get_widget("prefs-stats-enable-cpu").set_active(self.config.get_stats_enable_cpu_poll())

    def change_update_interval(self, src):
        self.config.set_stats_update_interval(src.get_value_as_int())

    def change_history_length(self, src):
        self.config.set_stats_history_length(src.get_value_as_int())

    def change_console_popup(self, box):
        self.config.set_console_popup(box.get_active())

    def change_console_keygrab(self, box):
        self.config.set_console_keygrab(box.get_active())

    def change_local_sound(self, src):
        self.config.set_local_sound(not self.config.get_local_sound())

    def change_remote_sound(self, src):
        self.config.set_remote_sound(not self.config.get_remote_sound())

    def change_disk_poll(self, src):
        self.config.set_stats_enable_disk_poll(src.get_active())
    def change_net_poll(self, src):
        self.config.set_stats_enable_net_poll(src.get_active())
    def change_mem_poll(self, src):
        self.config.set_stats_enable_mem_poll(src.get_active())
    def change_cpu_poll(self, src):
        self.config.set_stats_enable_cpu_poll(src.get_active())

    def show_help(self, src):
        # From the Preferences window, show the help document from
        # the Preferences page
        self.emit("action-show-help", "virt-manager-preferences-window")
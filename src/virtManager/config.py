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
import os
import logging

import gtk
import gconf

import libvirt
import virtinst

_spice_error = None
try:
    import SpiceClientGtk
    ignore = SpiceClientGtk
except Exception, _spice_error:
    logging.debug("Error importing spice: %s" % _spice_error)

from virtManager.keyring import vmmKeyring
from virtManager.secret import vmmSecret

CONSOLE_POPUP_NEVER = 0
CONSOLE_POPUP_NEW_ONLY = 1
CONSOLE_POPUP_ALWAYS = 2

CONSOLE_KEYGRAB_NEVER = 0
CONSOLE_KEYGRAB_FULLSCREEN = 1
CONSOLE_KEYGRAB_MOUSEOVER = 2

STATS_CPU = 0
STATS_DISK = 1
STATS_NETWORK = 2

DEFAULT_XEN_IMAGE_DIR = "/var/lib/xen/images"
DEFAULT_XEN_SAVE_DIR = "/var/lib/xen/dump"

DEFAULT_VIRT_IMAGE_DIR = "/var/lib/libvirt/images"
DEFAULT_VIRT_SAVE_DIR = "/var/lib/libvirt"

running_config = None

class vmmConfig(object):

    # GConf directory names for saving last used paths
    CONFIG_DIR_IMAGE = "image"
    CONFIG_DIR_MEDIA = "media"
    CONFIG_DIR_SAVE = "save"
    CONFIG_DIR_RESTORE = "restore"
    CONFIG_DIR_SCREENSHOT = "screenshot"

    # Metadata mapping for browse types. Prob shouldn't go here, but works
    # for now.
    browse_reason_data = {
        CONFIG_DIR_IMAGE : {
            "enable_create" : True,
            "storage_title" : _("Locate or create storage volume"),
            "local_title"   : _("Locate existing storage"),
        },

        CONFIG_DIR_MEDIA : {
            "enable_create" : False,
            "storage_title" : _("Locate ISO media volume"),
            "local_title"   : _("Locate ISO media"),
        }
    }

    CONSOLE_SCALE_NEVER = 0
    CONSOLE_SCALE_FULLSCREEN = 1
    CONSOLE_SCALE_ALWAYS = 2

    _PEROBJ_FUNC_SET    = 0
    _PEROBJ_FUNC_GET    = 1
    _PEROBJ_FUNC_LISTEN = 2

    def __init__(self, appname, appversion, gconf_dir, glade_dir, icon_dir,
                 data_dir):
        self.appname = appname
        self.appversion = appversion
        self.conf_dir = gconf_dir
        self.conf = gconf.client_get_default()
        self.conf.add_dir(gconf_dir,
                          gconf.CLIENT_PRELOAD_NONE)

        self.glade_dir = glade_dir
        self.icon_dir = icon_dir
        self.data_dir = data_dir

        # We don't create it straight away, since we don't want
        # to block the app pending user authorizaation to access
        # the keyring
        self.keyring = None

        self.default_qemu_user = "root"

        # Use this key to disable certain features not supported on RHEL
        self.enable_unsupported_rhel_opts = True
        self.preferred_distros = []
        self.hv_packages = []
        self.libvirt_packages = []

        self.status_icons = {
            libvirt.VIR_DOMAIN_BLOCKED: gtk.gdk.pixbuf_new_from_file_at_size(self.get_icon_dir() + "/state_running.png", 18, 18),
            libvirt.VIR_DOMAIN_CRASHED: gtk.gdk.pixbuf_new_from_file_at_size(self.get_icon_dir() + "/state_crashed.png", 18, 18),
            libvirt.VIR_DOMAIN_PAUSED: gtk.gdk.pixbuf_new_from_file_at_size(self.get_icon_dir() + "/state_paused.png", 18, 18),
            libvirt.VIR_DOMAIN_RUNNING: gtk.gdk.pixbuf_new_from_file_at_size(self.get_icon_dir() + "/state_running.png", 18, 18),
            libvirt.VIR_DOMAIN_SHUTDOWN: gtk.gdk.pixbuf_new_from_file_at_size(self.get_icon_dir() + "/state_shutoff.png", 18, 18),
            libvirt.VIR_DOMAIN_SHUTOFF: gtk.gdk.pixbuf_new_from_file_at_size(self.get_icon_dir() + "/state_shutoff.png", 18, 18),
            libvirt.VIR_DOMAIN_NOSTATE: gtk.gdk.pixbuf_new_from_file_at_size(self.get_icon_dir() + "/state_running.png", 18, 18),
            }
        self.status_icons_large = {
            libvirt.VIR_DOMAIN_BLOCKED: gtk.gdk.pixbuf_new_from_file_at_size(self.get_icon_dir() + "/state_running.png", 32, 32),
            libvirt.VIR_DOMAIN_CRASHED: gtk.gdk.pixbuf_new_from_file_at_size(self.get_icon_dir() + "/state_crashed.png", 32, 32),
            libvirt.VIR_DOMAIN_PAUSED: gtk.gdk.pixbuf_new_from_file_at_size(self.get_icon_dir() + "/state_paused.png", 32, 32),
            libvirt.VIR_DOMAIN_RUNNING: gtk.gdk.pixbuf_new_from_file_at_size(self.get_icon_dir() + "/state_running.png", 32, 32),
            libvirt.VIR_DOMAIN_SHUTDOWN: gtk.gdk.pixbuf_new_from_file_at_size(self.get_icon_dir() + "/state_shutoff.png", 32, 32),
            libvirt.VIR_DOMAIN_SHUTOFF: gtk.gdk.pixbuf_new_from_file_at_size(self.get_icon_dir() + "/state_shutoff.png", 32, 32),
            libvirt.VIR_DOMAIN_NOSTATE: gtk.gdk.pixbuf_new_from_file_at_size(self.get_icon_dir() + "/state_running.png", 32, 32),
            }


    # General app wide helpers (gconf agnostic)

    def get_vm_status_icon(self, state):
        return self.status_icons[state]

    def get_vm_status_icon_large(self, state):
        return self.status_icons_large[state]

    def get_shutdown_icon_name(self):
        theme = gtk.icon_theme_get_default()
        if theme.has_icon("system-shutdown"):
            return "system-shutdown"
        return "icon_shutdown"

    def get_appname(self):
        return self.appname

    def get_appversion(self):
        return self.appversion

    def get_glade_dir(self):
        return self.glade_dir

    def get_glade_file(self):
        return self.glade_dir + "/" + self.appname + ".glade"

    def get_icon_dir(self):
        return self.icon_dir

    def get_data_dir(self):
        return self.data_dir

    def get_spice_error(self):
        return _spice_error and str(_spice_error) or None

    def embeddable_graphics(self):
        ret = ["vnc"]
        if not bool(self.get_spice_error()):
            ret.append("spice")
        return ret

    # Per-VM/Connection/Connection Host Option dealings
    def _perconn_helper(self, uri, pref_func, func_type, value=None):
        suffix = "connection_prefs/%s" % gconf.escape_key(uri, len(uri))
        return self._perobj_helper(suffix, pref_func, func_type, value)
    def _perhost_helper(self, uri, pref_func, func_type, value=None):
        host = virtinst.util.get_uri_hostname(uri)
        if not host:
            host = "localhost"
        suffix = "connection_prefs/hosts/%s" % host
        return self._perobj_helper(suffix, pref_func, func_type, value)
    def _pervm_helper(self, uri, uuid, pref_func, func_type, value=None):
        suffix = ("connection_prefs/%s/vms/%s" %
                  (gconf.escape_key(uri, len(uri)), uuid))
        return self._perobj_helper(suffix, pref_func, func_type, value)

    def _perobj_helper(self, suffix, pref_func, func_type, value=None):
        # This function wraps the regular preference setting functions,
        # replacing conf_dir with a connection, host, or vm specific path. For
        # VMs, the path is:
        #
        # conf_dir/connection_prefs/{CONN_URI}/vms/{VM_UUID}
        #
        # So a per-VM pref will look like
        # .../connection_prefs/qemu:---system/vms/1234.../console/scaling
        #
        # Yeah this is evil but it's also nice and easy :)

        oldconf = self.conf_dir
        newconf = oldconf

        # Don't make a bogus gconf path if this is called nested.
        if not oldconf.count(suffix):
            newconf = "%s/%s" % (oldconf, suffix)

        ret = None
        try:
            self.conf_dir = newconf
            if func_type == self._PEROBJ_FUNC_SET:
                if type(value) is not tuple:
                    value = (value,)
                pref_func(*value)
            elif func_type == self._PEROBJ_FUNC_GET:
                ret = pref_func()
            elif func_type == self._PEROBJ_FUNC_LISTEN:
                pref_func(value)
        finally:
            self.conf_dir = oldconf

        return ret

    def set_pervm(self, uri, uuid, pref_func, args):
        """
        @param uri: VM connection URI
        @param uuid: VM UUID
        @param value: Set value or listener callback function
        @param pref_func: Global preference get/set/listen func that the
                          pervm instance will overshadow
        """
        self._pervm_helper(uri, uuid, pref_func, self._PEROBJ_FUNC_SET, args)
    def get_pervm(self, uri, uuid, pref_func):
        ret = self._pervm_helper(uri, uuid, pref_func, self._PEROBJ_FUNC_GET)
        if ret == None:
            # If the GConf value is unset, return the global default.
            ret = pref_func()
        return ret
    def listen_pervm(self, uri, uuid, pref_func, cb):
        self._pervm_helper(uri, uuid, pref_func, self._PEROBJ_FUNC_LISTEN, cb)

    def set_perconn(self, uri, pref_func, value):
        self._perconn_helper(uri, pref_func, self._PEROBJ_FUNC_SET, value)
    def get_perconn(self, uri, pref_func):
        ret = self._perconn_helper(uri, pref_func, self._PEROBJ_FUNC_GET)
        if ret == None:
            # If the GConf value is unset, return the global default.
            ret = pref_func()
        return ret
    def listen_perconn(self, uri, pref_func, cb):
        self._perconn_helper(uri, pref_func, self._PEROBJ_FUNC_LISTEN, cb)

    def set_perhost(self, uri, pref_func, value):
        self._perhost_helper(uri, pref_func, self._PEROBJ_FUNC_SET, value)
    def get_perhost(self, uri, pref_func):
        ret = self._perhost_helper(uri, pref_func, self._PEROBJ_FUNC_GET)
        if ret == None:
            # If the GConf value is unset, return the global default.
            ret = pref_func()
        return ret
    def listen_perhost(self, uri, pref_func, cb):
        self._perhost_helper(uri, pref_func, self._PEROBJ_FUNC_LISTEN, cb)

    def reconcile_vm_entries(self, uri, current_vms):
        """
        Remove any old VM preference entries for the passed URI
        """
        uri = gconf.escape_key(uri, len(uri))
        key = self.conf_dir + "/connection_prefs/%s/vms" % uri
        kill_vms = []
        gconf_vms = map(lambda inp: inp.split("/")[-1],
                        self.conf.all_dirs(key))

        for uuid in gconf_vms:
            if len(uuid) == 36 and not uuid in current_vms:
                kill_vms.append(uuid)

        for uuid in kill_vms:
            self.conf.recursive_unset(key + "/%s" % uuid, 0)

        if kill_vms:
            # Suggest gconf syncs, so that the unset dirs are fully removed
            self.conf.suggest_sync()

    #########################
    # General GConf helpers #
    #########################

    # Manager stats view preferences
    def is_vmlist_cpu_usage_visible(self):
        return self.conf.get_bool(self.conf_dir + "/vmlist-fields/cpu_usage")
    def is_vmlist_disk_io_visible(self):
        return self.conf.get_bool(self.conf_dir + "/vmlist-fields/disk_usage")
    def is_vmlist_network_traffic_visible(self):
        return self.conf.get_bool(self.conf_dir +
                                  "/vmlist-fields/network_traffic")

    def set_vmlist_cpu_usage_visible(self, state):
        self.conf.set_bool(self.conf_dir + "/vmlist-fields/cpu_usage", state)
    def set_vmlist_disk_io_visible(self, state):
        self.conf.set_bool(self.conf_dir + "/vmlist-fields/disk_usage", state)
    def set_vmlist_network_traffic_visible(self, state):
        self.conf.set_bool(self.conf_dir + "/vmlist-fields/network_traffic",
                           state)

    def on_vmlist_cpu_usage_visible_changed(self, cb):
        self.conf.notify_add(self.conf_dir + "/vmlist-fields/cpu_usage", cb)
    def on_vmlist_disk_io_visible_changed(self, cb):
        self.conf.notify_add(self.conf_dir + "/vmlist-fields/disk_usage", cb)
    def on_vmlist_network_traffic_visible_changed(self, cb):
        self.conf.notify_add(self.conf_dir + "/vmlist-fields/network_traffic",
                             cb)

    # Check whether we have GTK-VNC that supports configurable grab keys
    # installed on the system
    def vnc_grab_keys_supported(self):
        try:
            import gtkvnc
            return hasattr(gtkvnc.Display, "set_grab_keys")
        except:
            return False

    # Keys preferences
    def get_keys_combination(self, syms=False):
        val = self.conf.get_string(self.conf_dir + "/keys/grab-keys")
        if syms == True:
            return val

        # If val is None we return it
        if val is None:
            return None

        # We convert keysyms to names
        keystr = None
        for k in val.split(','):
            try:
                key = int(k)
            except:
                key = None

            if key is not None:
                if keystr is None:
                    keystr = gtk.gdk.keyval_name(key)
                else:
                    keystr = keystr + "+" + gtk.gdk.keyval_name(key)

        return keystr

    def set_keys_combination(self, val):
        # Val have to be a list of integers
        val = ','.join(map(str, val))
        self.conf.set_string(self.conf_dir + "/keys/grab-keys", val)

    # Confirmation preferences
    def get_confirm_forcepoweroff(self):
        return self.conf.get_bool(self.conf_dir + "/confirm/forcepoweroff")
    def get_confirm_poweroff(self):
        return self.conf.get_bool(self.conf_dir + "/confirm/poweroff")
    def get_confirm_pause(self):
        return self.conf.get_bool(self.conf_dir + "/confirm/pause")
    def get_confirm_removedev(self):
        return self.conf.get_bool(self.conf_dir + "/confirm/removedev")
    def get_confirm_interface(self):
        return self.conf.get_bool(self.conf_dir + "/confirm/interface_power")


    def set_confirm_forcepoweroff(self, val):
        self.conf.set_bool(self.conf_dir + "/confirm/forcepoweroff", val)
    def set_confirm_poweroff(self, val):
        self.conf.set_bool(self.conf_dir + "/confirm/poweroff", val)
    def set_confirm_pause(self, val):
        self.conf.set_bool(self.conf_dir + "/confirm/pause", val)
    def set_confirm_removedev(self, val):
        self.conf.set_bool(self.conf_dir + "/confirm/removedev", val)
    def set_confirm_interface(self, val):
        self.conf.set_bool(self.conf_dir + "/confirm/interface_power", val)

    def on_confirm_forcepoweroff_changed(self, cb):
        self.conf.notify_add(self.conf_dir + "/confirm/forcepoweroff", cb)
    def on_confirm_poweroff_changed(self, cb):
        self.conf.notify_add(self.conf_dir + "/confirm/poweroff", cb)
    def on_confirm_pause_changed(self, cb):
        self.conf.notify_add(self.conf_dir + "/confirm/pause", cb)
    def on_confirm_removedev_changed(self, cb):
        self.conf.notify_add(self.conf_dir + "/confirm/removedev", cb)
    def on_confirm_interface_changed(self, cb):
        self.conf.notify_add(self.conf_dir + "/confirm/interface_power", cb)


    # System tray visibility
    def on_view_system_tray_changed(self, callback):
        self.conf.notify_add(self.conf_dir + "/system-tray", callback)
    def get_view_system_tray(self):
        return self.conf.get_bool(self.conf_dir + "/system-tray")
    def set_view_system_tray(self, val):
        self.conf.set_bool(self.conf_dir + "/system-tray", val)


    # Stats history and interval length
    def get_stats_update_interval(self):
        interval = self.conf.get_int(self.conf_dir + "/stats/update-interval")
        if interval < 1:
            return 1
        return interval
    def get_stats_history_length(self):
        history = self.conf.get_int(self.conf_dir + "/stats/history-length")
        if history < 10:
            return 10
        return history

    def set_stats_update_interval(self, interval):
        self.conf.set_int(self.conf_dir + "/stats/update-interval", interval)
    def set_stats_history_length(self, length):
        self.conf.set_int(self.conf_dir + "/stats/history-length", length)

    def on_stats_update_interval_changed(self, callback):
        self.conf.notify_add(self.conf_dir + "/stats/update-interval", callback)
    def on_stats_history_length_changed(self, callback):
        self.conf.notify_add(self.conf_dir + "/stats/history-length", callback)


    # Disable/Enable different stats polling
    def get_stats_enable_disk_poll(self):
        return self.conf.get_bool(self.conf_dir + "/stats/enable-disk-poll")
    def get_stats_enable_net_poll(self):
        return self.conf.get_bool(self.conf_dir + "/stats/enable-net-poll")

    def set_stats_enable_disk_poll(self, val):
        self.conf.set_bool(self.conf_dir + "/stats/enable-disk-poll", val)
    def set_stats_enable_net_poll(self, val):
        self.conf.set_bool(self.conf_dir + "/stats/enable-net-poll", val)

    def on_stats_enable_disk_poll_changed(self, cb, userdata=None):
        self.conf.notify_add(self.conf_dir + "/stats/enable-disk-poll", cb,
                             userdata)
    def on_stats_enable_net_poll_changed(self, cb, userdata=None):
        self.conf.notify_add(self.conf_dir + "/stats/enable-net-poll", cb,
                             userdata)

    # VM Console preferences
    def on_console_popup_changed(self, callback):
        self.conf.notify_add(self.conf_dir + "/console/popup", callback)
    def get_console_popup(self):
        console_pref = self.conf.get_int(self.conf_dir + "/console/popup")
        if console_pref == None:
            console_pref = 0
        return console_pref
    def set_console_popup(self, pref):
        self.conf.set_int(self.conf_dir + "/console/popup", pref)

    def on_console_accels_changed(self, callback):
        self.conf.notify_add(self.conf_dir + "/console/enable-accels", callback)
    def get_console_accels(self):
        console_pref = self.conf.get_bool(self.conf_dir +
                                          "/console/enable-accels")
        if console_pref == None:
            console_pref = False
        return console_pref
    def set_console_accels(self, pref):
        self.conf.set_bool(self.conf_dir + "/console/enable-accels", pref)

    def on_console_scaling_changed(self, callback):
        self.conf.notify_add(self.conf_dir + "/console/scaling", callback)
    def get_console_scaling(self):
        ret = self.conf.get(self.conf_dir + "/console/scaling")
        if ret != None:
            ret = ret.get_int()
        return ret
    def set_console_scaling(self, pref):
        self.conf.set_int(self.conf_dir + "/console/scaling", pref)

    # Show VM details toolbar
    def get_details_show_toolbar(self):
        res = self.conf.get_bool(self.conf_dir + "/details/show-toolbar")
        if res == None:
            res = True
        return res
    def set_details_show_toolbar(self, state):
        self.conf.set_bool(self.conf_dir + "/details/show-toolbar", state)

    # VM details default size
    def get_details_window_size(self):
        w = self.conf.get_int(self.conf_dir + "/details/window_width")
        h = self.conf.get_int(self.conf_dir + "/details/window_height")
        return (w, h)
    def set_details_window_size(self, w, h):
        self.conf.set_int(self.conf_dir + "/details/window_width", w)
        self.conf.set_int(self.conf_dir + "/details/window_height", h)

    # Create sound device for default guest
    def get_local_sound(self):
        return self.conf.get_bool(self.conf_dir + "/new-vm/local-sound")
    def get_remote_sound(self):
        return self.conf.get_bool(self.conf_dir + "/new-vm/remote-sound")

    def set_local_sound(self, state):
        self.conf.set_bool(self.conf_dir + "/new-vm/local-sound", state)
    def set_remote_sound(self, state):
        self.conf.set_bool(self.conf_dir + "/new-vm/remote-sound", state)

    def on_sound_local_changed(self, cb, data=None):
        self.conf.notify_add(self.conf_dir + "/new-vm/local-sound", cb, data)
    def on_sound_remote_changed(self, cb, data=None):
        self.conf.notify_add(self.conf_dir + "/new-vm/remote-sound", cb, data)


    # URL/Media path history
    def _url_add_helper(self, gconf_path, url):
        urls = self.conf.get_list(gconf_path, gconf.VALUE_STRING)
        if urls == None:
            urls = []

        if urls.count(url) == 0 and len(url) > 0 and not url.isspace():
            # The url isn't already in the list, so add it
            urls.insert(0, url)
            length = self.get_url_list_length()
            if len(urls) > length:
                del urls[len(urls) - 1]
            self.conf.set_list(gconf_path, gconf.VALUE_STRING, urls)

    def add_media_url(self, url):
        self._url_add_helper(self.conf_dir + "/urls/media", url)
    def add_kickstart_url(self, url):
        self._url_add_helper(self.conf_dir + "/urls/kickstart", url)
    def add_iso_path(self, path):
        self._url_add_helper(self.conf_dir + "/urls/local_media", path)

    def get_media_urls(self):
        return self.conf.get_list(self.conf_dir + "/urls/media",
                                  gconf.VALUE_STRING)
    def get_kickstart_urls(self):
        return self.conf.get_list(self.conf_dir + "/urls/kickstart",
                                  gconf.VALUE_STRING)
    def get_iso_paths(self):
        return self.conf.get_list(self.conf_dir + "/urls/local_media",
                                 gconf.VALUE_STRING)

    def get_url_list_length(self):
        length = self.conf.get_int(self.conf_dir + "/urls/url-list-length")
        if length < 5:
            return 5
        return length
    def set_url_list_length(self, length):
        self.conf.set_int(self.conf_dir + "/urls/url-list-length", length)

    # Whether to ask about fixing path permissions
    def add_perms_fix_ignore(self, pathlist):
        current_list = self.get_perms_fix_ignore() or []
        for path in pathlist:
            if path in current_list:
                continue
            current_list.append(path)
        self.conf.set_list(self.conf_dir + "/paths/perms_fix_ignore",
                           gconf.VALUE_STRING,
                           current_list)
    def get_perms_fix_ignore(self):
        return self.conf.get_list(self.conf_dir + "/paths/perms_fix_ignore",
                                  gconf.VALUE_STRING)


    # Manager view connection list
    def add_connection(self, uri):
        uris = self.conf.get_list(self.conf_dir + "/connections/uris",
                                  gconf.VALUE_STRING)
        if uris == None:
            uris = []

        if uris.count(uri) == 0:
            uris.insert(len(uris) - 1, uri)
            self.conf.set_list(self.conf_dir + "/connections/uris",
                               gconf.VALUE_STRING, uris)
    def remove_connection(self, uri):
        uris = self.conf.get_list(self.conf_dir + "/connections/uris",
                                  gconf.VALUE_STRING)
        if uris == None:
            return

        if uris.count(uri) != 0:
            uris.remove(uri)
            self.conf.set_list(self.conf_dir + "/connections/uris",
                               gconf.VALUE_STRING, uris)

        if self.get_conn_autoconnect(uri):
            uris = self.conf.get_list(self.conf_dir +
                                      "/connections/autoconnect",
                                      gconf.VALUE_STRING)
            uris.remove(uri)
            self.conf.set_list(self.conf_dir + "/connections/autoconnect",
                               gconf.VALUE_STRING, uris)

    def get_connections(self):
        return self.conf.get_list(self.conf_dir + "/connections/uris",
                                  gconf.VALUE_STRING)

    # Manager default window size
    def get_manager_window_size(self):
        w = self.conf.get_int(self.conf_dir + "/manager_window_width")
        h = self.conf.get_int(self.conf_dir + "/manager_window_height")
        return (w, h)
    def set_manager_window_size(self, w, h):
        self.conf.set_int(self.conf_dir + "/manager_window_width", w)
        self.conf.set_int(self.conf_dir + "/manager_window_height", h)

    # URI autoconnect
    def get_conn_autoconnect(self, uri):
        uris = self.conf.get_list(self.conf_dir + "/connections/autoconnect",
                                  gconf.VALUE_STRING)
        return ((uris is not None) and (uri in uris))

    def set_conn_autoconnect(self, uri, val):
        uris = self.conf.get_list(self.conf_dir + "/connections/autoconnect",
                                  gconf.VALUE_STRING)
        if uris is None:
            uris = []
        if not val and uri in uris:
            uris.remove(uri)
        elif val and uri not in uris:
            uris.append(uri)

        self.conf.set_list(self.conf_dir + "/connections/autoconnect",
                           gconf.VALUE_STRING, uris)


    # Default directory location dealings
    def get_default_directory(self, conn, _type):
        if not _type:
            logging.error("Unknown type for get_default_directory")
            return

        try:
            path = self.conf.get_value(self.conf_dir + "/paths/default-%s-path"
                                                                       % _type)
        except:
            path = None

        if not path:
            if (_type == self.CONFIG_DIR_IMAGE or
                _type == self.CONFIG_DIR_MEDIA):
                path = self.get_default_image_dir(conn)
            if (_type == self.CONFIG_DIR_SAVE or
                _type == self.CONFIG_DIR_RESTORE):
                path = self.get_default_save_dir(conn)

        logging.debug("get_default_directory(%s): returning %s" % (_type, path))
        return path

    def set_default_directory(self, folder, _type):
        if not _type:
            logging.error("Unknown type for set_default_directory")
            return

        logging.debug("set_default_directory(%s): saving %s" % (_type, folder))
        self.conf.set_string(self.conf_dir + "/paths/default-%s-path" % _type,
                             folder)

    def get_default_image_dir(self, connection):
        if connection.is_xen():
            return DEFAULT_XEN_IMAGE_DIR

        if (connection.is_qemu_session() or
            not os.access(DEFAULT_VIRT_IMAGE_DIR, os.W_OK)):
            return os.getcwd()

        # Just return the default dir since the intention is that it
        # is a managed pool and the user will be able to install to it.
        return DEFAULT_VIRT_IMAGE_DIR

    def get_default_save_dir(self, connection):
        if connection.is_xen():
            return DEFAULT_XEN_SAVE_DIR
        elif os.access(DEFAULT_VIRT_SAVE_DIR, os.W_OK):
            return DEFAULT_VIRT_SAVE_DIR
        else:
            return os.getcwd()


    # Keyring / VNC password dealings
    def get_secret_name(self, vm):
        return "vm-console-" + vm.get_uuid()

    def has_keyring(self):
        if self.keyring == None:
            logging.warning("Initializing keyring")
            self.keyring = vmmKeyring()
        return self.keyring.is_available()

    def clear_console_password(self, vm):
        _id = self.conf.get_int(self.conf_dir + "/console/passwords/" + vm.get_uuid())

        if _id != None:
            if not(self.has_keyring()):
                return

            if self.keyring.clear_secret(_id):
                self.conf.unset(self.conf_dir + "/console/passwords/" + vm.get_uuid())

    def get_console_password(self, vm):
        _id = self.conf.get_int(self.conf_dir + "/console/passwords/" + vm.get_uuid())
        username = self.conf.get_string(self.conf_dir + "/console/usernames/" + vm.get_uuid())

        if username is None:
            username = ""

        if _id != None:
            if not(self.has_keyring()):
                return ("", "")

            secret = self.keyring.get_secret(_id)
            if secret != None and secret.get_name() == self.get_secret_name(vm):
                if not(secret.has_attribute("hvuri")):
                    return ("", "")
                if secret.get_attribute("hvuri") != vm.get_connection().get_uri():
                    return ("", "")
                if not(secret.has_attribute("uuid")):
                    return ("", "")
                if secret.get_attribute("uuid") != vm.get_uuid():
                    return ("", "")

                return (secret.get_secret(), username)
        return ("", username)

    def set_console_password(self, vm, password, username=""):
        if not(self.has_keyring()):
            return

        # Nb, we don't bother to check if there is an existing
        # secret, because gnome-keyring auto-replaces an existing
        # one if the attributes match - which they will since UUID
        # is our unique key

        secret = vmmSecret(self.get_secret_name(vm), password,
                           {"uuid" : vm.get_uuid(),
                            "hvuri": vm.get_connection().get_uri()})
        _id = self.keyring.add_secret(secret)
        if _id != None:
            self.conf.set_int(self.conf_dir + "/console/passwords/" + vm.get_uuid(), _id)
            self.conf.set_string(self.conf_dir + "/console/usernames/" + vm.get_uuid(), username)

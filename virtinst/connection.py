#
# Copyright 2013, 2014, 2015 Red Hat, Inc.
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

import logging
import weakref

import libvirt

from virtcli import CLIConfig

from . import pollhelpers
from . import support
from . import util
from . import Capabilities
from .guest import Guest
from .nodedev import NodeDevice
from .storage import StoragePool, StorageVolume
from .uri import URI, MagicURI


class VirtualConnection(object):
    """
    Wrapper for libvirt connection that provides various bits like
    - caching static data
    - lookup for API feature support
    - simplified API wrappers that handle new and old ways of doing things
    """
    def __init__(self, uri):
        _initial_uri = uri or ""

        if MagicURI.uri_is_magic(_initial_uri):
            self._magic_uri = MagicURI(_initial_uri)
            self._open_uri = self._magic_uri.open_uri
            self._uri = self._magic_uri.make_fake_uri()

            self._fake_conn_predictable = self._magic_uri.predictable
            self._fake_conn_remote = self._magic_uri.remote
            self._fake_conn_session = self._magic_uri.session
            self._fake_conn_version = self._magic_uri.conn_version
            self._fake_libvirt_version = self._magic_uri.libvirt_version
        else:
            self._magic_uri = None
            self._open_uri = _initial_uri
            self._uri = _initial_uri

            self._fake_conn_predictable = False
            self._fake_conn_remote = False
            self._fake_conn_session = False
            self._fake_libvirt_version = None
            self._fake_conn_version = None

        self._daemon_version = None
        self._conn_version = None

        self._libvirtconn = None
        self._uriobj = URI(self._uri)
        self._caps = None

        self._support_cache = {}
        self._fetch_cache = {}

        # These let virt-manager register a callback which provides its
        # own cached object lists, rather than doing fresh calls
        self.cb_fetch_all_guests = None
        self.cb_fetch_all_pools = None
        self.cb_fetch_all_vols = None
        self.cb_fetch_all_nodedevs = None
        self.cb_cache_new_pool = None


    ##############
    # Properties #
    ##############

    def __getattr__(self, attr):
        if attr in self.__dict__:
            return self.__dict__[attr]

        # Proxy virConnect API calls
        libvirtconn = self.__dict__.get("_libvirtconn")
        return getattr(libvirtconn, attr)

    def _get_uri(self):
        return self._uri or self._open_uri
    uri = property(_get_uri)

    def _get_caps(self):
        if not self._caps:
            self._caps = Capabilities(self,
                self._libvirtconn.getCapabilities())
        return self._caps
    caps = property(_get_caps)

    def get_conn_for_api_arg(self):
        return self._libvirtconn


    ##############
    # Public API #
    ##############

    def is_closed(self):
        return not bool(self._libvirtconn)

    def close(self):
        self._libvirtconn = None
        self._uri = None
        self._fetch_cache = {}

    def fake_conn_predictable(self):
        return self._fake_conn_predictable

    def invalidate_caps(self):
        self._caps = None

    def is_open(self):
        return bool(self._libvirtconn)

    def open(self, passwordcb):
        open_flags = 0
        valid_auth_options = [libvirt.VIR_CRED_AUTHNAME,
                              libvirt.VIR_CRED_PASSPHRASE]
        authcb = self._auth_cb
        authcb_data = passwordcb

        conn = libvirt.openAuth(self._open_uri,
                    [valid_auth_options, authcb,
                    (authcb_data, valid_auth_options)],
                    open_flags)

        if self._magic_uri:
            self._magic_uri.overwrite_conn_functions(conn)

        self._libvirtconn = conn
        if not self._open_uri:
            self._uri = self._libvirtconn.getURI()
            self._uriobj = URI(self._uri)

    def set_keep_alive(self, interval, count):
        if hasattr(self._libvirtconn, "setKeepAlive"):
            self._libvirtconn.setKeepAlive(interval, count)


    ####################
    # Polling routines #
    ####################

    _FETCH_KEY_GUESTS = "vms"
    _FETCH_KEY_POOLS = "pools"
    _FETCH_KEY_VOLS = "vols"
    _FETCH_KEY_NODEDEVS = "nodedevs"

    def _fetch_all_guests_raw(self):
        ignore, ignore, ret = pollhelpers.fetch_vms(
            self, {}, lambda obj, ignore: obj)
        return [Guest(weakref.ref(self), parsexml=obj.XMLDesc(0))
                for obj in ret]

    def fetch_all_guests(self):
        """
        Returns a list of Guest() objects
        """
        if self.cb_fetch_all_guests:
            return self.cb_fetch_all_guests()  # pylint: disable=not-callable

        key = self._FETCH_KEY_GUESTS
        if key not in self._fetch_cache:
            self._fetch_cache[key] = self._fetch_all_guests_raw()
        return self._fetch_cache[key][:]

    def _build_pool_raw(self, poolobj):
        return StoragePool(weakref.ref(self),
                           parsexml=poolobj.XMLDesc(0))

    def _fetch_all_pools_raw(self):
        ignore, ignore, ret = pollhelpers.fetch_pools(
            self, {}, lambda obj, ignore: obj)
        return [self._build_pool_raw(poolobj) for poolobj in ret]

    def fetch_all_pools(self):
        """
        Returns a list of StoragePool objects
        """
        if self.cb_fetch_all_pools:
            return self.cb_fetch_all_pools()  # pylint: disable=not-callable

        key = self._FETCH_KEY_POOLS
        if key not in self._fetch_cache:
            self._fetch_cache[key] = self._fetch_all_pools_raw()
        return self._fetch_cache[key][:]

    def _fetch_vols_raw(self, poolxmlobj):
        ret = []
        pool = self._libvirtconn.storagePoolLookupByName(poolxmlobj.name)
        if pool.info()[0] != libvirt.VIR_STORAGE_POOL_RUNNING:
            return ret

        ignore, ignore, vols = pollhelpers.fetch_volumes(
            self, pool, {}, lambda obj, ignore: obj)

        for vol in vols:
            try:
                xml = vol.XMLDesc(0)
                ret.append(StorageVolume(weakref.ref(self), parsexml=xml))
            except Exception as e:
                logging.debug("Fetching volume XML failed: %s", e)
        return ret

    def _fetch_all_vols_raw(self):
        ret = []
        for poolxmlobj in self.fetch_all_pools():
            ret.extend(self._fetch_vols_raw(poolxmlobj))
        return ret

    def fetch_all_vols(self):
        """
        Returns a list of StorageVolume objects
        """
        if self.cb_fetch_all_vols:
            return self.cb_fetch_all_vols()  # pylint: disable=not-callable

        key = self._FETCH_KEY_VOLS
        if key not in self._fetch_cache:
            self._fetch_cache[key] = self._fetch_all_vols_raw()
        return self._fetch_cache[key][:]

    def _cache_new_pool_raw(self, poolobj):
        # Make sure cache is primed
        if self._FETCH_KEY_POOLS not in self._fetch_cache:
            # Nothing cached yet, so next poll will pull in latest bits,
            # so there's nothing to do
            return

        poollist = self._fetch_cache[self._FETCH_KEY_POOLS]
        poolxmlobj = self._build_pool_raw(poolobj)
        poollist.append(poolxmlobj)

        if self._FETCH_KEY_VOLS not in self._fetch_cache:
            return
        vollist = self._fetch_cache[self._FETCH_KEY_VOLS]
        vollist.extend(self._fetch_vols_raw(poolxmlobj))

    def cache_new_pool(self, poolobj):
        """
        Insert the passed poolobj into our cache
        """
        if self.cb_cache_new_pool:
            # pylint: disable=not-callable
            return self.cb_cache_new_pool(poolobj)
        return self._cache_new_pool_raw(poolobj)

    def _fetch_all_nodedevs_raw(self):
        ignore, ignore, ret = pollhelpers.fetch_nodedevs(
            self, {}, lambda obj, ignore: obj)
        return [NodeDevice.parse(weakref.ref(self), obj.XMLDesc(0))
                for obj in ret]

    def fetch_all_nodedevs(self):
        """
        Returns a list of NodeDevice() objects
        """
        if self.cb_fetch_all_nodedevs:
            return self.cb_fetch_all_nodedevs()  # pylint: disable=not-callable

        key = self._FETCH_KEY_NODEDEVS
        if key not in self._fetch_cache:
            self._fetch_cache[key] = self._fetch_all_nodedevs_raw()
        return self._fetch_cache[key][:]


    #########################
    # Libvirt API overrides #
    #########################

    def getURI(self):
        return self._uri


    #########################
    # Public version checks #
    #########################

    def local_libvirt_version(self):
        if self._fake_libvirt_version is not None:
            return self._fake_libvirt_version
        # This handles caching for us
        return util.local_libvirt_version()

    def daemon_version(self):
        if self._fake_libvirt_version is not None:
            return self._fake_libvirt_version
        if not self.is_remote():
            return self.local_libvirt_version()

        if not self._daemon_version:
            if not self.check_support(support.SUPPORT_CONN_LIBVERSION):
                self._daemon_version = 0
            else:
                self._daemon_version = self._libvirtconn.getLibVersion()
        return self._daemon_version

    def conn_version(self):
        if self._fake_conn_version is not None:
            return self._fake_conn_version

        if not self._conn_version:
            if not self.check_support(support.SUPPORT_CONN_GETVERSION):
                self._conn_version = 0
            else:
                self._conn_version = self._libvirtconn.getVersion()
        return self._conn_version

    def stable_defaults(self, emulator=None, force=False):
        """
        :param force: Just check if we are running on RHEL, regardless of
            whether stable defaults are requested by the build. This is needed
            to ensure we don't enable VM devices that are compiled out on
            RHEL, like vmvga
        """
        if not CLIConfig.stable_defaults and not force:
            return False

        if not self.is_qemu():
            return False

        if emulator:
            return str(emulator).startswith("/usr/libexec")

        for guest in self.caps.guests:
            for dom in guest.domains:
                if dom.emulator.startswith("/usr/libexec"):
                    return True
        return False


    ###################
    # Public URI bits #
    ###################

    def is_remote(self):
        return (self._fake_conn_remote or self._uriobj.hostname)
    def is_session_uri(self):
        return (self._fake_conn_session or self.get_uri_path() == "/session")

    def get_uri_hostname(self):
        return self._uriobj.hostname
    def get_uri_port(self):
        return self._uriobj.port
    def get_uri_username(self):
        return self._uriobj.username
    def get_uri_transport(self):
        if self.get_uri_hostname() and not self._uriobj.transport:
            # Libvirt defaults to transport=tls if hostname specified but
            # no transport is specified
            return "tls"
        return self._uriobj.transport
    def get_uri_path(self):
        return self._uriobj.path

    def get_uri_driver(self):
        return self._uriobj.scheme

    def is_qemu(self):
        return self._uriobj.scheme.startswith("qemu")
    def is_qemu_system(self):
        return (self.is_qemu() and self._uriobj.path == "/system")
    def is_qemu_session(self):
        return (self.is_qemu() and self.is_session_uri())

    def is_really_test(self):
        return URI(self._open_uri).scheme.startswith("test")
    def is_test(self):
        return self._uriobj.scheme.startswith("test")
    def is_xen(self):
        return (self._uriobj.scheme.startswith("xen") or
                self._uriobj.scheme.startswith("libxl"))
    def is_lxc(self):
        return self._uriobj.scheme.startswith("lxc")
    def is_openvz(self):
        return self._uriobj.scheme.startswith("openvz")
    def is_container(self):
        return self.is_lxc() or self.is_openvz()
    def is_vz(self):
        return (self._uriobj.scheme.startswith("vz") or
                self._uriobj.scheme.startswith("parallels"))


    #########################
    # Support check helpers #
    #########################

    for _supportname in [_supportname for _supportname in dir(support) if
                         _supportname.startswith("SUPPORT_")]:
        locals()[_supportname] = getattr(support, _supportname)

    def check_support(self, feature, data=None):
        key = feature
        data = data or self
        if key not in self._support_cache:
            self._support_cache[key] = support.check_support(
                self, feature, data)
        return self._support_cache[key]

    def support_remote_url_install(self):
        if self._magic_uri:
            return False
        return (self.check_support(self.SUPPORT_CONN_STREAM) and
                self.check_support(self.SUPPORT_STREAM_UPLOAD))


    ###################
    # Private helpers #
    ###################

    def _auth_cb(self, creds, data):
        passwordcb, passwordcreds = data
        for cred in creds:
            if cred[0] not in passwordcreds:
                raise RuntimeError("Unknown cred type '%s', expected only "
                                   "%s" % (cred[0], passwordcreds))
        return passwordcb(creds)

#
# Copyright 2006, 2013 Red Hat, Inc.
# Jeremy Katz <katzj@redhat.com>
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
import os
import random
import re
import stat

import libvirt
import libxml2


_host_blktap_capable = None


def listify(l):
    if l is None:
        return []
    elif type(l) != list:
        return [l]
    else:
        return l


def xml_indent(xmlstr, level):
    xml = ""
    if not xmlstr:
        return xml
    if not level:
        return xmlstr
    return "\n".join((" " * level + l) for l in xmlstr.splitlines())


def stat_disk(path):
    """Returns the tuple (isreg, size)."""
    if not os.path.exists(path):
        return True, 0

    mode = os.stat(path)[stat.ST_MODE]

    # os.path.getsize('/dev/..') can be zero on some platforms
    if stat.S_ISBLK(mode):
        try:
            fd = os.open(path, os.O_RDONLY)
            # os.SEEK_END is not present on all systems
            size = os.lseek(fd, 0, 2)
            os.close(fd)
        except:
            size = 0
        return False, size
    elif stat.S_ISREG(mode):
        return True, os.path.getsize(path)

    return True, 0


def blkdev_size(path):
    """Return the size of the block device.  We can't use os.stat() as
    that returns zero on many platforms."""
    fd = os.open(path, os.O_RDONLY)
    # os.SEEK_END is not present on all systems
    size = os.lseek(fd, 0, 2)
    os.close(fd)
    return size


def sanitize_arch(arch):
    """Ensure passed architecture string is the format we expect it.
       Returns the sanitized result"""
    if not arch:
        return arch
    tmparch = arch.lower().strip()
    if re.match(r'i[3-9]86', tmparch):
        return "i686"
    elif tmparch == "amd64":
        return "x86_64"
    return arch


def vm_uuid_collision(conn, uuid):
    """
    Check if passed UUID string is in use by another guest of the connection
    Returns true/false
    """
    return libvirt_collision(conn.lookupByUUIDString, uuid)


def libvirt_collision(collision_cb, val):
    """
    Run the passed collision function with val as the only argument:
    If libvirtError is raised, return False
    If no libvirtError raised, return True
    """
    check = False
    if val is not None:
        try:
            if collision_cb(val) is not None:
                check = True
        except libvirt.libvirtError:
            pass
    return check


def validate_uuid(val):
    if type(val) is not str:
        raise ValueError(_("UUID must be a string."))

    form = re.match("[a-fA-F0-9]{8}[-]([a-fA-F0-9]{4}[-]){3}[a-fA-F0-9]{12}$",
                    val)
    if form is None:
        form = re.match("[a-fA-F0-9]{32}$", val)
        if form is None:
            raise ValueError(
                  _("UUID must be a 32-digit hexadecimal number. It may take "
                    "the form xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx or may "
                    "omit hyphens altogether."))

        else:   # UUID had no dashes, so add them in
            val = (val[0:8] + "-" + val[8:12] + "-" + val[12:16] +
                   "-" + val[16:20] + "-" + val[20:32])
    return val


def validate_name(name_type, val):
    # Rather than try and match libvirt's regex, just forbid things we
    # know don't work
    forbid = [" "]
    for c in forbid:
        if c not in val:
            continue
        raise ValueError(
            _("%s name '%s' can not contain '%s' character.") %
            (name_type, val, c))


def validate_macaddr(val):
    if val is None:
        return

    if type(val) is not str:
        raise ValueError(_("MAC address must be a string."))

    form = re.match("^([0-9a-fA-F]{1,2}:){5}[0-9a-fA-F]{1,2}$", val)
    if form is None:
        raise ValueError(_("MAC address must be of the format "
                           "AA:BB:CC:DD:EE:FF, was '%s'") % val)


def generate_name(base, collision_cb, suffix="", lib_collision=True,
                  start_num=1, sep="-", force_num=False, collidelist=None):
    """
    Generate a new name from the passed base string, verifying it doesn't
    collide with the collision callback.

    This can be used to generate disk path names from the parent VM or pool
    name. Names generated look like 'base-#suffix', ex:

    If foobar, and foobar-1.img already exist, and:
    base   = "foobar"
    suffix = ".img"

    output = "foobar-2.img"

    @param base: The base string to use for the name (e.g. "my-orig-vm-clone")
    @param collision_cb: A callback function to check for collision,
        receives the generated name as its only arg
    @param lib_collision: If true, the collision_cb is not a boolean function,
        and instead throws a libvirt error on failure
    @param start_num: The number to start at for generating non colliding names
    @param sep: The seperator to use between the basename and the
        generated number (default is "-")
    @param force_num: Force the generated name to always end with a number
    @param collidelist: An extra list of names to check for collision
    """
    collidelist = collidelist or []

    def collide(n):
        if n in collidelist:
            return True
        if lib_collision:
            return libvirt_collision(collision_cb, tryname)
        else:
            return collision_cb(tryname)

    numrange = range(start_num, start_num + 100000)
    if not force_num:
        numrange = [None] + numrange

    for i in numrange:
        tryname = base
        if i is not None:
            tryname += ("%s%d" % (sep, i))
        tryname += suffix

        if not collide(tryname):
            return tryname

    raise ValueError(_("Name generation range exceeded."))


def default_bridge(conn):
    if conn.is_remote():
        return None

    dev = default_route()
    if not dev:
        return None

    # New style peth0 == phys dev, eth0 == bridge, eth0 == default route
    if os.path.exists("/sys/class/net/%s/bridge" % dev):
        return ["bridge", dev]

    # Old style, peth0 == phys dev, eth0 == netloop, xenbr0 == bridge,
    # vif0.0 == netloop enslaved, eth0 == default route
    try:
        defn = int(dev[-1])
    except:
        defn = -1

    if (defn >= 0 and
        os.path.exists("/sys/class/net/peth%d/brport" % defn) and
        os.path.exists("/sys/class/net/xenbr%d/bridge" % defn)):
        return ["bridge", "xenbr%d" % defn]
    return None


def parse_node_helper(xml, root_name, callback, exec_class=ValueError):
    """
    Parse the passed XML, expecting root as root_name, and pass the
    root node to callback
    """
    class ErrorHandler(object):
        def __init__(self):
            self.msg = ""
        def handler(self, ignore, s):
            self.msg += s
    error = ErrorHandler()
    libxml2.registerErrorHandler(error.handler, None)

    try:
        try:
            doc = libxml2.readMemory(xml, len(xml),
                                     None, None,
                                     libxml2.XML_PARSE_NOBLANKS)
        except (libxml2.parserError, libxml2.treeError), e:
            raise exec_class("%s\n%s" % (e, error.msg))
    finally:
        libxml2.registerErrorHandler(None, None)

    ret = None
    try:
        root = doc.getRootElement()
        if root.name != root_name:
            raise ValueError("Root element is not '%s'" % root_name)

        ret = callback(root)
    finally:
        doc.freeDoc()

    return ret


def generate_uuid(conn):
    for ignore in range(256):
        uuid = randomUUID(conn)
        if not vm_uuid_collision(conn, uuid):
            return uuid

    logging.error("Failed to generate non-conflicting UUID")



def default_route():
    route_file = "/proc/net/route"
    d = file(route_file)

    defn = 0
    for line in d.xreadlines():
        info = line.split()
        if (len(info) != 11):  # 11 = typical num of fields in the file
            logging.warn(_("Invalid line length while parsing %s."),
                         route_file)
            logging.warn(_("Defaulting bridge to xenbr%d"), defn)
            break
        try:
            route = int(info[1], 16)
            if route == 0:
                return info[0]
        except ValueError:
            continue
    return None


def default_network(conn):
    ret = default_bridge(conn)
    if not ret:
        # FIXME: Check that this exists
        ret = ["network", "default"]

    return ret


def is_blktap_capable(conn):
    # Ideally we would get this from libvirt capabilities XML
    if conn.is_remote():
        return False

    global _host_blktap_capable
    if _host_blktap_capable is not None:
        return _host_blktap_capable

    lines = file("/proc/modules").readlines()
    for line in lines:
        if line.startswith("blktap ") or line.startswith("xenblktap "):
            _host_blktap_capable = True
            break

    if not _host_blktap_capable:
        _host_blktap_capable = False
    return _host_blktap_capable


def randomUUID(conn):
    if hasattr(conn, "_virtinst__fake_conn_predictable"):
        # Testing hack
        return "00000000-1111-2222-3333-444444444444"

    u = [random.randint(0, 255) for ignore in range(0, 16)]
    u[6] = (u[6] & 0x0F) | (4 << 4)
    u[8] = (u[8] & 0x3F) | (2 << 6)
    return "-".join(["%02x" * 4, "%02x" * 2, "%02x" * 2, "%02x" * 2,
                     "%02x" * 6]) % tuple(u)


def xml_escape(xml):
    """
    Replaces chars ' " < > & with xml safe counterparts
    """
    if xml is None:
        return None

    xml = xml.replace("&", "&amp;")
    xml = xml.replace("'", "&apos;")
    xml = xml.replace("\"", "&quot;")
    xml = xml.replace("<", "&lt;")
    xml = xml.replace(">", "&gt;")
    return xml


def uri_split(uri):
    """
    Parse a libvirt hypervisor uri into it's individual parts
    @returns: tuple of the form (scheme (ex. 'qemu', 'xen+ssh'), username,
                                 hostname, path (ex. '/system'), query,
                                 fragment)
    """
    def splitnetloc(url, start=0):
        for c in '/?#':  # the order is important!
            delim = url.find(c, start)
            if delim >= 0:
                break
        else:
            delim = len(url)
        return url[start:delim], url[delim:]

    username = netloc = query = fragment = ''
    i = uri.find(":")
    if i > 0:
        scheme, uri = uri[:i].lower(), uri[i + 1:]
        if uri[:2] == '//':
            netloc, uri = splitnetloc(uri, 2)
            offset = netloc.find("@")
            if offset > 0:
                username = netloc[0:offset]
                netloc = netloc[offset + 1:]
        if '#' in uri:
            uri, fragment = uri.split('#', 1)
        if '?' in uri:
            uri, query = uri.split('?', 1)
    else:
        scheme = uri.lower()
    return scheme, username, netloc, uri, query, fragment


def is_error_nosupport(err):
    """
    Check if passed exception indicates that the called libvirt command isn't
    supported

    @param err: Exception raised from command call
    @returns: True if command isn't supported, False if we can't determine
    """
    if not isinstance(err, libvirt.libvirtError):
        return False

    if (err.get_error_code() == libvirt.VIR_ERR_RPC or
        err.get_error_code() == libvirt.VIR_ERR_NO_SUPPORT):
        return True

    return False


def exception_is_libvirt_error(e, error):
    return (hasattr(libvirt, error) and
            e.get_error_code() == getattr(libvirt, error))


def local_libvirt_version():
    """
    Lookup the local libvirt library version, but cache the value since
    it never changes.
    """
    key = "__virtinst_cached_getVersion"
    if not hasattr(libvirt, key):
        setattr(libvirt, key, libvirt.getVersion())
    return getattr(libvirt, key)


def uuidstr(rawuuid):
    hx = ['0', '1', '2', '3', '4', '5', '6', '7',
          '8', '9', 'a', 'b', 'c', 'd', 'e', 'f']
    uuid = []
    for i in range(16):
        uuid.append(hx[((ord(rawuuid[i]) >> 4) & 0xf)])
        uuid.append(hx[(ord(rawuuid[i]) & 0xf)])
        if i == 3 or i == 5 or i == 7 or i == 9:
            uuid.append('-')
    return "".join(uuid)




def get_system_scratchdir(hvtype):
    if "VIRTINST_TEST_SUITE" in os.environ:
        return os.getcwd()

    if hvtype == "test":
        return "/tmp"
    elif hvtype == "xen":
        return "/var/lib/xen"
    else:
        return "/var/lib/libvirt/boot"


def make_scratchdir(conn, hvtype):
    scratch = None
    if not conn.is_session_uri():
        scratch = get_system_scratchdir(hvtype)

    if (not scratch or
        not os.path.exists(scratch) or
        not os.access(scratch, os.W_OK)):
        scratch = os.path.join(get_cache_dir(), "boot")
        if not os.path.exists(scratch):
            os.makedirs(scratch, 0751)

    return scratch


def pretty_mem(val):
    val = int(val)
    if val > (10 * 1024 * 1024):
        return "%2.2f GB" % (val / (1024.0 * 1024.0))
    else:
        return "%2.0f MB" % (val / 1024.0)


def pretty_bytes(val):
    val = int(val)
    if val > (1024 * 1024 * 1024):
        return "%2.2f GB" % (val / (1024.0 * 1024.0 * 1024.0))
    else:
        return "%2.2f MB" % (val / (1024.0 * 1024.0))


def get_cache_dir():
    ret = ""
    try:
        # We don't want to depend on glib for virt-install
        from gi.repository import GLib  # pylint: disable=E0611
        ret = GLib.get_user_cache_dir()
    except ImportError:
        pass

    if not ret:
        ret = os.environ.get("XDG_CACHE_HOME")
    if not ret:
        ret = os.path.expanduser("~/.cache")
    return os.path.join(ret, "virt-manager")


def convert_units(value, old_unit, new_unit):
    def get_factor(unit):
        factor = 1000
        if unit[-2:] == 'ib':
            factor = 1024
        return factor

    def get_power(unit):
        powers = ('k', 'm', 'g', 't', 'p', 'e')
        power = 0
        if unit[0] in powers:
            power = powers.index(unit[0]) + 1
        return power

    # First convert it all into bytes
    factor = get_factor(old_unit)
    power = get_power(old_unit)
    in_bytes = value * pow(factor, power)

    # Then convert it to the target unit
    factor = get_factor(new_unit)
    power = get_power(new_unit)

    return in_bytes / pow(factor, power)

#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free  Software Foundation; either version 2 of the License, or
# (at your option)  any later version.
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

import unittest
import libvirt
import virtinst
import virtinst.cli
import virtinst.ImageParser
import os

from tests import utils

qemuuri = "__virtinst_test__test:///default,caps=%s/tests/capabilities-xml/capabilities-kvm.xml,qemu,predictable" % os.getcwd()


# pylint: disable=W0212
# Access to protected member, needed to unittest stuff

class TestImageParser(unittest.TestCase):

    basedir = "tests/image-xml/"
    conn = libvirt.open("test:///default")
    qemuconn = virtinst.cli.open_test_uri(qemuuri)
    caps = virtinst.CapabilitiesParser.parse(conn.getCapabilities())
    qemucaps = virtinst.CapabilitiesParser.parse(qemuconn.getCapabilities())

    def testImageParsing(self):
        f = open(os.path.join(self.basedir, "image.xml"), "r")
        xml = f.read()
        f.close()

        img = virtinst.ImageParser.parse(xml, ".")
        self.assertEqual("test-image", img.name)
        self.assertTrue(img.domain)
        self.assertEqual(5, len(img.storage))
        self.assertEqual(2, len(img.domain.boots))
        self.assertEqual(1, img.domain.interface)
        boot = img.domain.boots[0]
        self.assertEqual("xvdb", boot.drives[1].target)

    def testMultipleNics(self):
        f = open(os.path.join(self.basedir, "image2nics.xml"), "r")
        xml = f.read()
        f.close()

        img = virtinst.ImageParser.parse(xml, ".")
        self.assertEqual(2, img.domain.interface)

    def testBadArch(self):
        """Makes sure we sanitize i386->i686"""
        image = virtinst.ImageParser.parse_file(self.basedir +
                                                "image-bad-arch.xml")
        virtinst.ImageInstaller(image, self.caps, 0)
        self.assertTrue(True)

    def testStorageFormat(self):
        self._image2XMLhelper("image-format.xml", "image-format-out.xml",
                              qemu=True)

    def _image2XMLhelper(self, image_xml, output_xmls, qemu=False):
        image2guestdir = self.basedir + "image2guest/"
        image = virtinst.ImageParser.parse_file(self.basedir + image_xml)
        if type(output_xmls) is not list:
            output_xmls = [output_xmls]

        conn = qemu and self.qemuconn or self.conn
        caps = qemu and self.qemucaps or self.caps
        gtype = qemu and "qemu" or "xen"

        for idx in range(len(output_xmls)):
            fname = output_xmls[idx]
            inst = virtinst.ImageInstaller(image, caps, boot_index=idx,
                                           conn=conn)

            utils.set_conn(conn)

            if inst.is_hvm():
                g = utils.get_basic_fullyvirt_guest(typ=gtype)
            else:
                g = utils.get_basic_paravirt_guest()

            g.installer = inst
            g._prepare_install(None)

            actual_out = g.get_xml_config(install=False)
            expect_file = os.path.join(image2guestdir + fname)
            expect_out = utils.read_file(expect_file)
            expect_out = expect_out.replace("REPLACEME", os.getcwd())

            utils.diff_compare(actual_out,
                               expect_file,
                               expect_out=expect_out)

            utils.reset_conn()

    def testImage2XML(self):
        # Build libvirt XML from the image xml
        self._image2XMLhelper("image.xml", ["image-xenpv32.xml",
                                            "image-xenfv32.xml"])
        self._image2XMLhelper("image-kernel.xml", ["image-xenpv32-kernel.xml"])

if __name__ == "__main__":
    unittest.main()

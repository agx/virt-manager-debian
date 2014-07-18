# -*- rpm-spec -*-


%define with_guestfs               0
%define stable_defaults            0
%define askpass_package            "openssh-askpass"
%define qemu_user                  "qemu"
%define libvirt_packages           "libvirt-daemon-kvm,libvirt-daemon-config-network"
%define preferred_distros          "fedora,rhel"
%define kvm_packages               "qemu-system-x86"

%if 0%{?rhel}
%define preferred_distros          "rhel,fedora"
%define kvm_packages               "qemu-kvm"
%define stable_defaults            1
%endif


# End local config


# This macro is used for the continuous automated builds. It just
# allows an extra fragment based on the timestamp to be appended
# to the release. This distinguishes automated builds, from formal
# Fedora RPM builds
%define _extra_release %{?dist:%{dist}}%{?extra_release:%{extra_release}}

Name: virt-manager
Version: 1.0.1
Release: 1%{_extra_release}
%define verrel %{version}-%{release}

Summary: Virtual Machine Manager
Group: Applications/Emulators
License: GPLv2+
URL: http://virt-manager.org/
Source0: http://virt-manager.org/download/sources/%{name}/%{name}-%{version}.tar.gz
BuildArch: noarch


Requires: virt-manager-common = %{verrel}
Requires: pygobject3
Requires: gtk3
Requires: libvirt-glib >= 0.0.9
Requires: libxml2-python
Requires: vte3
Requires: dconf
Requires: dbus-x11

# For console widget
Requires: gtk-vnc2
Requires: spice-gtk3


BuildRequires: intltool
BuildRequires: /usr/bin/pod2man


%description
Virtual Machine Manager provides a graphical tool for administering virtual
machines for KVM, Xen, and LXC. Start, stop, add or remove virtual devices,
connect to a graphical or serial console, and see resource usage statistics
for existing VMs on local or remote machines. Uses libvirt as the backend
management API.


%package common
Summary: Common files used by the different Virtual Machine Manager interfaces
Group: Applications/Emulators

# This version not strictly required: virt-manager should work with older,
# however varying amounts of functionality will not be enabled.
Requires: libvirt-python >= 0.7.0
Requires: libxml2-python
Requires: python-urlgrabber
Requires: python-ipaddr

%description common
Common files used by the different virt-manager interfaces, as well as
virt-install related tools.


%package -n virt-install
Summary: Utilities for installing virtual machines

Requires: virt-manager-common = %{verrel}

Provides: virt-install
Provides: virt-clone
Provides: virt-image
Provides: virt-convert
Provides: virt-xml
Obsoletes: python-virtinst

%description -n virt-install
Package includes several command line utilities, including virt-install
(build and install new VMs) and virt-clone (clone an existing virtual
machine).


%prep
%setup -q

%build
%if %{qemu_user}
%define _qemu_user --qemu-user=%{qemu_user}
%endif

%if %{kvm_packages}
%define _kvm_packages --kvm-package-names=%{kvm_packages}
%endif

%if %{preferred_distros}
%define _preferred_distros --preferred-distros=%{preferred_distros}
%endif

%if %{libvirt_packages}
%define _libvirt_packages --libvirt-package-names=%{libvirt_packages}
%endif

%if %{askpass_package}
%define _askpass_package --askpass-package-names=%{askpass_package}
%endif

%if %{stable_defaults}
%define _stable_defaults --stable-defaults
%endif

python setup.py configure \
    --pkgversion="%{version}" \
    %{?_qemu_user} \
    %{?_kvm_packages} \
    %{?_libvirt_packages} \
    %{?_askpass_package} \
    %{?_preferred_distros} \
    %{?_stable_defaults}


%install
python setup.py install -O1 --root=$RPM_BUILD_ROOT

%find_lang %{name}


%post
/bin/touch --no-create %{_datadir}/icons/hicolor &>/dev/null || :
/usr/bin/update-desktop-database &> /dev/null || :


%postun
if [ $1 -eq 0 ] ; then
    /bin/touch --no-create %{_datadir}/icons/hicolor &>/dev/null
    /usr/bin/gtk-update-icon-cache %{_datadir}/icons/hicolor &>/dev/null || :
    /usr/bin/glib-compile-schemas %{_datadir}/glib-2.0/schemas &> /dev/null || :
fi
/usr/bin/update-desktop-database &> /dev/null || :


%posttrans
/usr/bin/gtk-update-icon-cache %{_datadir}/icons/hicolor &>/dev/null || :
/usr/bin/glib-compile-schemas %{_datadir}/glib-2.0/schemas &> /dev/null || :


%files
%doc README COPYING NEWS
%{_bindir}/%{name}

%{_mandir}/man1/%{name}.1*

%{_datadir}/%{name}/ui/*.ui
%{_datadir}/%{name}/virt-manager
%{_datadir}/%{name}/virtManager

%{_datadir}/%{name}/icons
%{_datadir}/icons/hicolor/*/apps/*

%{_datadir}/appdata/%{name}.appdata.xml
%{_datadir}/applications/%{name}.desktop
%{_datadir}/glib-2.0/schemas/org.virt-manager.virt-manager.gschema.xml


%files common -f %{name}.lang
%dir %{_datadir}/%{name}

%{_datadir}/%{name}/virtcli
%{_datadir}/%{name}/virtconv
%{_datadir}/%{name}/virtinst


%files -n virt-install
%{_mandir}/man1/virt-install.1*
%{_mandir}/man1/virt-clone.1*
%{_mandir}/man1/virt-convert.1*
%{_mandir}/man1/virt-xml.1*
%{_mandir}/man1/virt-image.1*
%{_mandir}/man5/virt-image.5*

%{_datadir}/%{name}/virt-install
%{_datadir}/%{name}/virt-clone
%{_datadir}/%{name}/virt-image
%{_datadir}/%{name}/virt-convert
%{_datadir}/%{name}/virt-xml

%{_bindir}/virt-install
%{_bindir}/virt-clone
%{_bindir}/virt-image
%{_bindir}/virt-convert
%{_bindir}/virt-xml


%changelog
* Sat Mar 22 2014 Cole Robinson <crobinso@redhat.com> - 1.0.1-1
- virt-manager release 1.0.1
- virt-install/virt-xml: New --memorybacking option (Chen Hanxiao)
- virt-install/virt-xml: New --memtune option (Chen Hanxiao)
- virt-manager: UI for LXC <idmap> (Chen Hanxiao)
- virt-manager: gsettings key to disable keygrab (Kjö Hansi Glaz)
- virt-manager: Show domain state reason in the UI (Giuseppe Scrivano)
- Fix a number of bugs found since the 1.0.0 release

* Fri Feb 14 2014 Cole Robinson <crobinso@redhat.com> - 1.0.0-1
- virt-manager release 1.0.0
- virt-manager: Snapshot support
- New tool virt-xml: Edit libvirt XML in one shot from the command line
- Improved defaults: qcow2, USB2, host CPU model, guest agent channel,
  ...
- Introspect command line options like --disk=? or --network=help
- The virt-image tool will be removed before the next release, speak up
  if you have a good reason not to remove it.
- virt-manager: Support arm vexpress VM creation
- virt-manager: Add guest memory usage graphs (Thorsten Behrens)
- virt-manager: UI for editing <filesystem> devices (Cédric Bosdonnat)
- Spice USB redirection support (Guannan Ren)
- <tpm> UI and command line support (Stefan Berger)
- <rng> UI and command line support (Giuseppe Scrivano)
- <panic> UI and command line support (Chen Hanxiao)
- <blkiotune> command line support (Chen Hanxiao)
- virt-manager: support for glusterfs storage pools (Giuseppe Scrivano)
- cli: New options --memory, --features, --clock, --metadata, --pm
- Greatly improve app responsiveness when connecting to remote hosts
- Lots of UI cleanup and improvements

* Wed Jun 19 2013 Cole Robinson <crobinso@redhat.com> - 0.10.0-1
- virt-manager release 0.10.0
- Merged code with python-virtinst. virtinst is no longer public
- Port from GTK2 to GTK3 (Daniel Berrange, Cole Robinson)
- Port from gconf to gsettings
- Port from autotools to python distutils
- Remove virt-manager-tui
- Remove HAL support
- IPv6 and static route virtual network support (Gene Czarcinski)
- virt-install: Add --cpu host-passthrough (Ken ICHIKAWA, Hu Tao)

* Mon Apr 01 2013 Cole Robinson <crobinso@redhat.com> - 0.9.5-1
- virt-manager release 0.9.5
- Enable adding virtio-scsi disks (Chen Hanxiao)
- Support security auto-relabel setting (Martin Kletzander)
- Support disk iotune settings (David Shane Holden)
- Support 'reset' as a reboot option (John Doyle)
- Bug fixes and minor improvements

* Sun Jul 29 2012 Cole Robinson <crobinso@redhat.com> - 0.9.4-1
- virt-manager release 0.9.4
- Fix VNC keygrab issues

* Mon Jul 09 2012 Cole Robinson <crobinso@redhat.com> - 0.9.3-1
- virt-manager release 0.9.3
- Fix broken release tar.gz of version 0.9.2

* Mon Jul 09 2012 Cole Robinson <crobinso@redhat.com> - 0.9.2-1
- virt-manager release 0.9.2
- Convert to gtkbuilder: UI can now be edited with modern glade tool
- virt-manager no longer runs on RHEL5, but can manage a remote RHEL5
  host
- Option to configure spapr net and disk devices for pseries (Li Zhang)
- Many bug fixes and improvements

* Tue Jan 31 2012 Cole Robinson <crobinso@redhat.com> - 0.9.1-1
- Support for adding usb redirection devices (Marc-André Lureau)
- Option to switch usb controller to support usb2.0 (Marc-André Lureau)
- Option to specify machine type for non-x86 guests (Li Zhang)
- Support for filesystem device type and write policy (Deepak C Shetty)
- Many bug fixes!

* Tue Jul 26 2011 Cole Robinson <crobinso@redhat.com> - 0.9.0-1
- Use a hiding toolbar for fullscreen mode
- Use libguestfs to show guest packagelist and more (Richard W.M. Jones)
- Basic 'New VM' wizard support for LXC guests
- Remote serial console access (with latest libvirt)
- Remote URL guest installs (with latest libvirt)
- Add Hardware: Support <filesystem> devices
- Add Hardware: Support <smartcard> devices (Marc-André Lureau)
- Enable direct interface selection for qemu/kvm (Gerhard Stenzel)
- Allow viewing and changing disk serial number

* Thu Mar 24 2011 Cole Robinson <crobinso@redhat.com> - 0.8.7-1
- Allow renaming an offline VM
- Spice password support (Marc-André Lureau)
- Allow editting NIC <virtualport> settings (Gerhard Stenzel)
- Allow enabling/disabling individual CPU features
- Allow easily changing graphics type between VNC and SPICE for existing
  VM
- Allow easily changing network source device for existing VM

* Fri Jan 14 2011 Cole Robinson <crobinso@redhat.com> - 0.8.6-1
- SPICE support (requires spice-gtk) (Marc-André Lureau)
- Option to configure CPU model
- Option to configure CPU topology
- Save and migration cancellation (Wen Congyang)
- Save and migration progress reporting
- Option to enable bios boot menu
- Option to configure direct kernel/initrd boot

* Tue Aug 24 2010 Cole Robinson <crobinso@redhat.com> - 0.8.5-1
- Improved save/restore support
- Option to view and change disk cache mode
- Configurable VNC keygrab sequence (Michal Novotny)

* Wed Mar 24 2010 Cole Robinson <crobinso@redhat.com> - 0.8.4-1
- 'Import' install option, to create a VM around an existing OS image
- Support multiple boot devices and boot order
- Watchdog device support
- Enable setting a human readable VM description.
- Option to manually specifying a bridge name, if bridge isn't detected

* Mon Feb  8 2010 Cole Robinson <crobinso@redhat.com> - 0.8.3-1
- Manage network interfaces: start, stop, view, provision bridges, bonds, etc.
- Option to 'customize VM before install'.

* Mon Dec 14 2009 Cole Robinson <crobinso@redhat.com> - 0.8.2-1
- Fix right click in the manager window to operate on the clicked row
- Running on a new machine / user account no longer produces a traceback.
- Allow ejecting and connecting floppy media

* Thu Dec  3 2009 Cole Robinson <crobinso@redhat.com> - 0.8.1-1
- VM Migration wizard, exposing various migration options
- Enumerate CDROM and bridge devices on remote connections
- Support storage pool source enumeration for LVM, NFS, and SCSI

* Tue Jul 28 2009 Cole Robinson <crobinso@redhat.com> - 0.8.0-1
- New 'Clone VM' Wizard
- Improved UI, including an overhaul of the main 'manager' view
- System tray icon for easy VM access (start, stop, view console/details)
- Wizard for adding serial, parallel, and video devices to existing VMs.

* Mon Mar  9 2009 Cole Robinson <crobinso@redhat.com> - 0.7.0-1
- Redesigned 'New Virtual Machine' wizard (Jeremy Perry, Cole Robinson)
- Option to remove storage when deleting a virtual machine.
- File browser for libvirt storage pools and volumes
- Physical device assignment (PCI, USB) for existing virtual machines.

* Mon Jan 26 2009 Cole Robinson <crobinso@redhat.com> - 0.6.1-1
- VM disk and network stats reporting (Guido Gunther)
- VM Migration support (Shigeki Sakamoto)
- Support for adding sound devices to an existing VM
- Enumerate host devices attached to an existing VM

* Wed Sep 10 2008 Cole Robinson <crobinso@redhat.com> - 0.6.0-1
- Add libvirt storage management support
- Basic support for remote guest installation
- Merge VM console and details windows
- Poll avahi for libvirtd advertisement
- Hypervisor autoconnect option
- Add sound emulation when creating new guests

* Mon Mar 10 2008 Daniel P Berrange <berrange@redhat.com> - 0.5.4-1
- Use capabilities XML when creating guests
- Allow scaling of VNC window

* Thu Jan 10 2008 Daniel P Berrange <berrange@redhat.com> - 0.5.3-1
- Reintroduce 'new' button
- Make restore work again
- Add menu for sending special keys
- Fix license headers on all source
- Lots of misc bug fixes

* Thu Oct  4 2007 Daniel P. Berrange <berrange@redhat.com> - 0.5.2-1
- No scrollbars for high res guest in low res host (rhbz 273181)
- Unable to remove network device (rhbz 242900)
- Fixed broken menu items (rhbz 307551)
- Allow adding of graphics console (rhbz 215524)

* Tue Sep 25 2007 Daniel P. Berrange <berrange@redhat.com> - 0.5.1-1
- Open connections in background
- Make VNC connection retries more robust
- Allow changing of CDROM media on the fly
- Add PXE boot installation of HVM guests
- Allow tunnelling VNC over SSH

* Wed Aug 29 2007 Daniel P. Berrange <berrange@redhat.com> - 0.5.0-1
- Support for managing remote hosts
- Switch to use GTK-VNC for the guest console

* Mon Apr 16 2007 Daniel P. Berrange <berrange@redhat.com> - 0.4.0-1
- Support for managing virtual networks
- Ability to attach guest to virtual networks
- Automatically set VNC keymap based on local keymap
- Support for disk & network device addition/removal

* Tue Mar 20 2007 Daniel P. Berrange <berrange@redhat.com> - 0.3.2-1
- Added online help to all windows
- Bug fixes to virtual console popup, key grab & accelerator override

* Tue Feb 20 2007 Daniel P. Berrange <berrange@redhat.com> - 0.3.1-1
- Added support for managing QEMU domains
- Automatically grab mouse pointer to workaround dual-cursor crazyness

* Mon Jan 22 2007 Daniel P. Berrange <berrange@redhat.com> - 0.3.0-1
- Added support for managing inactive domains
- Require virt-inst >= 0.100.0 and libvirt >= 0.1.11 for ianctive
  domain management capabilities
- Add progress bars during VM creation stage
- Improved reliability of VNC console
- Updated translations again
- Added destroy option to menu bar to forceably kill a guest
- Visually differentiate allocated memory, from actual used memory on host
- Validate file magic when restoring a guest from a savd file
- Performance work on domain listing
- Allow creation of non-sparse files
- Fix backspace key in serial console

* Thu Nov  9 2006 Daniel P. Berrange <berrange@redhat.com> - 0.2.6-1
- Imported translations from Fedora i18n repository
- Make (most) scrollbar policies automatic
- Set busy cursor while creating new VMs
- Preference for controlling keygrab policy
- Preference for when to automatically open console (bz 211385)
- Re-try VNC connection attempt periodically in case VNC daemon
  hasn't finished starting up
- Added activation of URLs for about dialog (bz 210782)
- Improved error reporting when connecting to HV (bz 211229)
- Add command line args to open specific windows
- Don't skip para/full virt wizard step - instead gray out full
  virt option & tell user why
- Change 'physical' to 'logical' when refering to host CPUs
- Include hostname in titlebar
- Disable wizard sensitivity while creating VM

* Thu Oct 19 2006 Daniel P. Berrange <berrange@redhat.com> - 0.2.5-1
- Switch to use python-virtinst instead of python-xeninst due to
  renaming of original package
- Disable keyboard accelerators when grabbing mouse to avoid things like
  Ctrl-W closing the local window, instead of remote window bz 210364
- Fix host memory reporting bz 211281
- Remove duplicate application menu entry bz 211230

* Thu Oct 12 2006 Daniel Berrange <berrange@redhat.com> - 0.2.4-1
- Fix duplicated mnemonics (bz 208408)
- Use blktap backed disks if available
- Use a drop down list to remember past URLs (bz 209479)
- Remove unused help button from preferences dialog (bz 209251)
- Fix exception when no VNC graphics is defined
- Force immediate refresh of VMs after creating a new one
- Improve error reporting if run on a kernel without Xen (bz 209122)
- Clamp CPU utilization between 0 & 100 pcent (bz 208185)
- Fix array underflow SEGV when no data points available (bz 208185)
- More fixes to avoid stuck modifier keys on focus-out (bz 207949)

* Tue Sep 26 2006 Daniel Berrange <berrange@redhat.com> - 0.2.3-1
- Require xeninst >= 0.93.0 to fix block backed devices
- Skip para/fully-virt step when going back in wizard if not HVM host (bz 207409)
- Fix handling of modifier keys in VNC console so Alt key doesn't get stuck (bz 207949)
- Allow sticky modifier keys by pressing same key 3 times in row (enables Ctrl-Alt-F1
  by doing Ctrl Ctrl Ctrl  Alt-F1)
- Improved error handling during guest creation
- Log errors with python logging, instead of to stdout
- Remove unused buttons from main domain list window
- Switch out of full screen & release key grab when closing console
- Trim sparkline CPU history graph to 40 samples max
- Constraint VCPU adjuster to only allow upto guest's max VCPU count
- Show guest's max & current VCPU count in details page
- Fix rounding of disk sizes to avoid a 1.9 GB disk being rounded down to 1 GB
- Use raw block device path to CDROM not mount point for HVM guest (bz 206965)
- Fix visibility of file size spin box (bz 206186 part 2)
- Check for GTK failing to open X11 display (bz 205938)

* Fri Sep 15 2006 Daniel Berrange <berrange@redhat.com> - 0.2.2-1
- Fix event handling in create VM wizard (bz 206660 & 206186)
- Fix close button in about dialog (bz 205943)
- Refresh .pot files
- Turn on VNC scrollbars fulltime to avoid GTK window sizing issue
  which consistently resize too small.

* Mon Sep 11 2006 Daniel Berrange <berrange@redhat.com> - 0.2.1-3
- Added requires on pygtk2-libglade & librsvg2 (bz 205941 & 205942)
- Re-arrange to use console-helper to launch app
- Added 'dist' component to release number

* Wed Sep  6 2006 Jeremy Katz <katzj@redhat.com> - 0.2.1-2
- don't ghost pyo files (#205448)

* Mon Sep  4 2006 Daniel Berrange <berrange@redhat.com> - 0.2.1-1
- Updated to 0.2.1 tar.gz
- Added rules to install/uninstall gconf schemas in preun,post,pre
  scriptlets

* Thu Aug 24 2006 Jeremy Katz <katzj@redhat.com> - 0.2.0-3
- BR gettext

* Thu Aug 24 2006 Jeremy Katz <katzj@redhat.com> - 0.2.0-2
- only build on arches with virt

* Tue Aug 22 2006 Daniel Berrange <berrange@redhat.com> - 0.2.0-1
- Added wizard for creating virtual machines
- Added embedded serial console
- Added ability to take screenshots

* Mon Jul 24 2006 Daniel Berrange <berrange@redhat.com> - 0.1.5-2
- Prefix *.pyo files with 'ghost' macro
- Use fully qualified URL in Source  tag

* Thu Jul 20 2006 Daniel Berrange <berrange@redhat.com> - 0.1.5-1
- Update to new 0.1.5 release snapshot

* Thu Jul 20 2006 Daniel Berrange <berrange@redhat.com> - 0.1.4-1
- Update to new 0.1.4 release snapshot

* Mon Jul 17 2006 Daniel Berrange <berrange@redhat.com> - 0.1.3-1
- Fix License tag
- Updated for new release

* Wed Jun 28 2006 Daniel Berrange <berrange@redhat.com> - 0.1.2-3
- Added missing copyright headers on all .py files

* Wed Jun 28 2006 Daniel Berrange <berrange@redhat.com> - 0.1.2-2
- Added python-devel to BuildRequires

* Wed Jun 28 2006 Daniel Berrange <berrange@redhat.com> - 0.1.2-1
- Change URL to public location

* Fri Jun 16 2006 Daniel Berrange <berrange@redhat.com> - 0.1.0-1
- Added initial support for using VNC console

* Thu Apr 20 2006 Daniel Berrange <berrange@redhat.com> - 0.0.2-1
- Added DBus remote control service

* Wed Mar 29 2006 Daniel Berrange <berrange@redhat.com> - 0.0.1-1
- Initial RPM build

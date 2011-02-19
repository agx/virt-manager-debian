# -*- rpm-spec -*-

# This macro is used for the continuous automated builds. It just
# allows an extra fragment based on the timestamp to be appended
# to the release. This distinguishes automated builds, from formal
# Fedora RPM builds
%define _extra_release %{?dist:%{dist}}%{!?dist:%{?extra_release:%{extra_release}}}

Name: virt-manager
Version: 0.8.6
Release: 1%{_extra_release}
Summary: Virtual Machine Manager

Group: Applications/Emulators
License: GPLv2+
URL: http://virt-manager.org/
Source0: http://virt-manager.org/download/sources/%{name}/%{name}-%{version}.tar.gz
BuildRoot: %{_tmppath}/%{name}-%{version}-%{release}-root-%(%{__id_u} -n)
BuildArch: noarch

# These two are just the oldest version tested
Requires: pygtk2 >= 1.99.12-6
Requires: gnome-python2-gconf >= 1.99.11-7
# This version not strictly required: virt-manager should work with older,
# however varying amounts of functionality will not be enabled.
Requires: libvirt-python >= 0.7.0
# Definitely does not work with earlier due to python API changes
Requires: dbus-python >= 0.61
Requires: dbus-x11
# Might work with earlier, but this is what we've tested
Requires: gnome-keyring >= 0.4.9
# Minimum we've tested with
# Although if you don't have this, comment it out and the app
# will work just fine - keyring functionality will simply be
# disabled
Requires: gnome-python2-gnomekeyring >= 2.15.4
# Minimum we've tested with
Requires: libxml2-python >= 2.6.23
# Absolutely require this version or later
Requires: python-virtinst >= 0.500.5
# Required for loading the glade UI
Requires: pygtk2-libglade
# Required for our graphics which are currently SVG format
Requires: librsvg2
# Earlier vte had broken python binding module
Requires: vte >= 0.12.2
# For online help
Requires: scrollkeeper
# For console widget
Requires: gtk-vnc-python >= 0.3.8
# For local authentication against PolicyKit
# Fedora 12 has no need for a client agent
%if 0%{?fedora} == 11
Requires: PolicyKit-authentication-agent
%endif
%if 0%{?fedora} >= 9 && 0%{?fedora} < 11
Requires: PolicyKit-gnome
%endif

BuildRequires: gettext
BuildRequires: scrollkeeper
BuildRequires: intltool

Requires(pre): GConf2
Requires(post): GConf2
Requires(preun): GConf2
Requires(post): desktop-file-utils
Requires(postun): desktop-file-utils

%description
Virtual Machine Manager provides a graphical tool for administering virtual
machines for KVM, Xen, and QEmu. Start, stop, add or remove virtual devices,
connect to a graphical or serial console, and see resource usage statistics
for existing VMs on local or remote machines. Uses libvirt as the backend
management API.

%prep
%setup -q

%build
%configure --without-tui
make %{?_smp_mflags}


%install
rm -rf $RPM_BUILD_ROOT
make install  DESTDIR=$RPM_BUILD_ROOT
%find_lang %{name}

%clean
rm -rf $RPM_BUILD_ROOT

%pre
if [ "$1" -gt 1 ]; then
    export GCONF_CONFIG_SOURCE=`gconftool-2 --get-default-source`
    gconftool-2 --makefile-uninstall-rule \
      %{_sysconfdir}/gconf/schemas/%{name}.schemas > /dev/null || :
fi

%post
export GCONF_CONFIG_SOURCE=`gconftool-2 --get-default-source`
gconftool-2 --makefile-install-rule \
  %{_sysconfdir}/gconf/schemas/%{name}.schemas > /dev/null || :

update-desktop-database %{_datadir}/applications

# Revive when we update help docs
#if which scrollkeeper-update>/dev/null 2>&1; then scrollkeeper-update -q -o %{_datadir}/omf/%{name}; fi

%postun
update-desktop-database %{_datadir}/applications

# Revive when we update help docs
#if which scrollkeeper-update>/dev/null 2>&1; then scrollkeeper-update -q; fi

%preun
if [ "$1" -eq 0 ]; then
    export GCONF_CONFIG_SOURCE=`gconftool-2 --get-default-source`
    gconftool-2 --makefile-uninstall-rule \
      %{_sysconfdir}/gconf/schemas/%{name}.schemas > /dev/null || :
fi

%files -f %{name}.lang
%defattr(-,root,root,-)
%doc README COPYING COPYING-DOCS AUTHORS ChangeLog NEWS
%{_sysconfdir}/gconf/schemas/%{name}.schemas
%{_bindir}/%{name}
%{_libexecdir}/%{name}-launch

%{_mandir}/man1/%{name}.1*

%dir %{_datadir}/%{name}
%{_datadir}/%{name}/*.glade
%{_datadir}/%{name}/*.py*

%dir %{_datadir}/%{name}/pixmaps/
%{_datadir}/%{name}/pixmaps/*.png
%{_datadir}/%{name}/pixmaps/*.svg

%dir %{_datadir}/%{name}/pixmaps/hicolor/
%dir %{_datadir}/%{name}/pixmaps/hicolor/*/
%dir %{_datadir}/%{name}/pixmaps/hicolor/*/*/
%{_datadir}/%{name}/pixmaps/hicolor/*/*/*.png

%dir %{_datadir}/%{name}/virtManager/
%{_datadir}/%{name}/virtManager/*.py*

# Revive when we update help docs
#%{_datadir}/omf/%{name}/
#%{_datadir}/gnome/help/%{name}

%{_datadir}/applications/%{name}.desktop
%{_datadir}/dbus-1/services/%{name}.service

%changelog
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

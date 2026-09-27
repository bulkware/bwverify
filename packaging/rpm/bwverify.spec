Name:           bwverify
Version:        1.0.0
Release:        1%{?dist}
Summary:        A desktop application for verifying file integrity using checksum files.

# Keep build and runtime dependencies separate so minimal installations remain small.
License:        GPL-3.0-or-later
URL:            https://github.com/bulkware/bwverify
Source0:        %{name}-%{version}.tar.gz
BuildArch:      noarch

BuildRequires:  python3-devel
BuildRequires:  python3-setuptools
BuildRequires:  python3dist(pygobject)
BuildRequires:  gtk4
BuildRequires:  make
BuildRequires:  pyproject-rpm-macros
BuildRequires:  desktop-file-utils
BuildRequires:  appstream
BuildRequires:  shared-mime-info
Requires:       python3-gobject
Requires:       gtk4

%description
A desktop application for verifying file integrity using checksum files.

# The wrapper supplies a complete, versioned source archive to this standard RPM layout.
%prep
%autosetup

%build
%pyproject_wheel

%check
PYTHONPATH=src %{python3} -m unittest discover -s tests -v

%install
%pyproject_install
# Install desktop integration explicitly because Python wheel data excludes these assets.
install -D -m 644 data/org.bulkware.bwverify.desktop \
    %{buildroot}%{_datadir}/applications/org.bulkware.bwverify.desktop
install -D -m 644 data/org.bulkware.bwverify.metainfo.xml \
    %{buildroot}%{_metainfodir}/org.bulkware.bwverify.metainfo.xml
install -D -m 644 data/org.bulkware.bwverify.xml \
    %{buildroot}%{_datadir}/mime/packages/org.bulkware.bwverify.xml
install -D -m 644 data/icons/hicolor/scalable/apps/org.bulkware.bwverify.svg \
    %{buildroot}%{_datadir}/icons/hicolor/scalable/apps/org.bulkware.bwverify.svg
install -D -m 644 data/icons/hicolor/symbolic/apps/org.bulkware.bwverify-symbolic.svg \
    %{buildroot}%{_datadir}/icons/hicolor/symbolic/apps/org.bulkware.bwverify-symbolic.svg

%files
# List every integration asset so RPM ownership and uninstall behaviour stay correct.
%license LICENSE.md
%doc CHANGELOG.md README.md
%{_bindir}/bwverify
%{python3_sitelib}/bwverify
%{python3_sitelib}/bwverify-*.dist-info
%{_datadir}/applications/org.bulkware.bwverify.desktop
%{_metainfodir}/org.bulkware.bwverify.metainfo.xml
%{_datadir}/mime/packages/org.bulkware.bwverify.xml
%{_datadir}/icons/hicolor/scalable/apps/org.bulkware.bwverify.svg
%{_datadir}/icons/hicolor/symbolic/apps/org.bulkware.bwverify-symbolic.svg

%changelog
* Sat Sep 19 2026 Antti-Pekka Meronen <antice@kapsi.fi> - 1.0.0-1
- Added: Initial release.

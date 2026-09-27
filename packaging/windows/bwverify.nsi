!ifndef VERSION
  !error "VERSION must be provided."
!endif
!ifndef APP_DIR
  !error "APP_DIR must be provided."
!endif
!ifndef OUT_DIR
  !error "OUT_DIR must be provided."
!endif

; Keep shared registry paths short and consistent across installation and removal.
!define UNINSTALL_KEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\bwVerify"
!define FILE_CLASS_KEY "Software\Classes\bwVerify.ChecksumFile"

; Basic installer identity and a per-user destination avoid elevation requirements.
Name "bwVerify ${VERSION}"
OutFile "${OUT_DIR}\bwverify-${VERSION}-setup.exe"
InstallDir "$LOCALAPPDATA\Programs\bwVerify"
InstallDirRegKey HKCU "Software\bwVerify" "InstallDir"
RequestExecutionLevel user

!include "LogicLib.nsh"

Page directory
Page instfiles
UninstPage uninstConfirm
UninstPage instfiles

Section "bwVerify" SEC_MAIN
  ; Copy the self-contained PyInstaller folder before registering its entry points.
  SetOutPath "$INSTDIR"
  File /r "${APP_DIR}\*"

  ; Register the program and uninstaller in the current user's application list.
  WriteRegStr HKCU "Software\bwVerify" "InstallDir" "$INSTDIR"
  WriteRegStr HKCU "${UNINSTALL_KEY}" "DisplayName" "bwVerify"
  WriteRegStr HKCU "${UNINSTALL_KEY}" "DisplayVersion" "${VERSION}"
  WriteRegStr HKCU "${UNINSTALL_KEY}" "UninstallString" '"$INSTDIR\Uninstall.exe"'
  WriteRegDWORD HKCU "${UNINSTALL_KEY}" "NoModify" 1
  WriteRegDWORD HKCU "${UNINSTALL_KEY}" "NoRepair" 1
  WriteUninstaller "$INSTDIR\Uninstall.exe"

  ; Add Start menu shortcuts without creating a system-wide group.
  CreateDirectory "$SMPROGRAMS\bwVerify"
  CreateShortcut "$SMPROGRAMS\bwVerify\bwVerify.lnk" "$INSTDIR\bwVerify.exe"
  CreateShortcut "$SMPROGRAMS\bwVerify\Uninstall bwVerify.lnk" "$INSTDIR\Uninstall.exe"
SectionEnd

Section /o "Associate checksum files" SEC_ASSOC
  ; Optional associations let Explorer pass supported manifests to the installed app.
  WriteRegStr HKCU "${FILE_CLASS_KEY}" "" "bwVerify checksum file"
  WriteRegStr HKCU "${FILE_CLASS_KEY}\shell\open\command" "" '"$INSTDIR\bwVerify.exe" "%1"'
  WriteRegStr HKCU "Software\Classes\.sfv" "" "bwVerify.ChecksumFile"
  WriteRegStr HKCU "Software\Classes\.md5" "" "bwVerify.ChecksumFile"
  WriteRegStr HKCU "Software\Classes\.sha256" "" "bwVerify.ChecksumFile"
  System::Call 'shell32::SHChangeNotify(i 0x8000000, i 0, p 0, p 0)'
SectionEnd

Section "Uninstall"
  ; Remove shortcuts and program registration before deleting the application folder.
  Delete "$SMPROGRAMS\bwVerify\bwVerify.lnk"
  Delete "$SMPROGRAMS\bwVerify\Uninstall bwVerify.lnk"
  RMDir "$SMPROGRAMS\bwVerify"

  DeleteRegKey HKCU "${UNINSTALL_KEY}"
  DeleteRegKey HKCU "Software\bwVerify"
  ReadRegStr $0 HKCU "Software\Classes\.sfv" ""
  ${If} $0 == "bwVerify.ChecksumFile"
    DeleteRegKey HKCU "Software\Classes\.sfv"
  ${EndIf}
  ReadRegStr $0 HKCU "Software\Classes\.md5" ""
  ${If} $0 == "bwVerify.ChecksumFile"
    DeleteRegKey HKCU "Software\Classes\.md5"
  ${EndIf}
  ReadRegStr $0 HKCU "Software\Classes\.sha256" ""
  ${If} $0 == "bwVerify.ChecksumFile"
    DeleteRegKey HKCU "Software\Classes\.sha256"
  ${EndIf}
  ; Preserve an extension reassigned by another application after installation.
  DeleteRegKey HKCU "${FILE_CLASS_KEY}"
  System::Call 'shell32::SHChangeNotify(i 0x8000000, i 0, p 0, p 0)'
  RMDir /r "$INSTDIR"
SectionEnd

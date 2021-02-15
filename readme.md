# SIM808 for Raspberry Pi

This is a class for basic use of the SIM808 GSM/GPRS/GPS module with python on Raspberry Pi.

It should run on any system with Python and most functions should work with the other SIMCom modules as well.

*This is a work in progress and free to use/modify for anyone. It comes with absolutely no warranty, use at your own risk.*

## Functionality implemented so far

- Send/receive SMS
- Upload/download files to/from FTP server
- Create/Delete Directories on FTP server
- Delete files on FTP server
- Check/change network operator
- Read GPS data
- List contents of ftp directory (though currently gives server error if there are too many items)
- Read file size from FTP server and use for validation of successful file transfer
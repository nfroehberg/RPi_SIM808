# SIM808 for Raspberry Pi

This is a class for basic use of the SIM808 GSM/GPRS/GPS module with python on Raspberry Pi.

It should run on any system with Python and most functions should work with the other SIMCom modules as well. Focus of development is reliability rather than speed for autonomous operation in embedded systems.

*This is a work in progress and free to use/modify for anyone. It comes with absolutely no warranty, use at your own risk.*

## Functionality implemented so far

- Send/receive SMS
- Upload/download files to/from FTP server
- Create/Delete Directories on FTP server
- Delete files on FTP server
- Check/change network operator
- Read GPS data
- List contents of ftp directory
- Read file size from FTP server and use for validation of successful file transfer
- use slow clock standby mode to save power (requires use of DTR pin on RPi GPIO)
- turn power on/off through GPIO
- sending emails (without attachments)

## How To's

### Emails

Sending emails was tested to work with GMail and GMX. Both require ssl to be enabled. In GMail, you need to activate access for less secure apps.

In order to not be considered spam by recipient server, the time needs to be set correctly. Use `clock_network_sync()` and restart the module before sending emails (needs to be done once).

*Email attachments have not been implemented yet.*

```python
sim.email_parameters(apn="INTERNET.EPLUS.DE", server='smtp.gmail.com',port=465,user='username',pwd='password', sender_address='my_address@gmail.com', sender_name='My Name', ssl=1)
sim.email_initialize()
subject='Test'
message='This is a test message.'
sim.email_send(subject,message,'recipient_address@gmail.com','Recipient Name')
```
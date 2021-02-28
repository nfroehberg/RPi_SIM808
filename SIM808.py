# Python driver for the SIMCom SIM808 GSM/GPRS/GPS module
# Nico Fröhberg, 2021
# nico.froehberg@gmx.de
# feel free to use and adapt as you like
# only tested on SIM808 but should also work with other SIMCOM chips like SIM800 or SIM900
# potentially also with others using the AT command protocol

import time, serial, re

if __name__=="__main__":
    # initiate object
    sim = SIM808()
    # check network
    print(sim.network_get_registration())
    # check reception
    print(sim.check_signal())
    # check SMS messages
    for message in sim.sms_get():
        print(message)
    # send test SMS
    sim.sms_send("1234567890","Test message")
    # delete SMS with ID 2
    sim.sms_delete(2)
    # set up ftp parameters
    sim.ftp_parameters(apn="INTERNET.EPLUS.DE", server="", port=21, user="", pwd="")
    sim.ftp_initialize()
    # create directory on FTP server
    sim.ftp_dir_create_delete('test_dir2',True)
    # upload file
    sim.ftp_file_send(file="test_file.txt",dir="/test_dir/")

class SIM808():
    
    def __init__(self, port="/dev/ttyAMA0", baud=115200, t_out=1, rtscts=False, xonxoff=False, dtr_pin=0, pwr_pin=0):
        self.port = serial.Serial(port, baudrate=baud, timeout=t_out)
        self.ftp_errors = {1:'No Error',61:'Net Error',62:'DNS Error',63:'Connect Error',64:'Timeout',
                            65:'Server Error',66:'Operation not allowed', 70:'Replay Error',71:'User Error',
                            72:'Password Error',73:'Type Error',74:'Rest Error',75:'Passive error',
                            76:'Active error',77:'Operate Error',78:'Upload Error',79:'Download Error',
                            86:'Manual Quit'}
        self.dtr_pin = dtr_pin
        if dtr_pin != 0:
            import RPi.GPIO
            self.gpio = RPi.GPIO
            self.gpio.setmode(self.gpio.BOARD)
            self.gpio.setup(self.dtr_pin, self.gpio.OUT)      
        self.pwr_pin = pwr_pin
        if pwr_pin != 0:
            import RPi.GPIO
            self.gpio = RPi.GPIO
            self.gpio.setmode(self.gpio.BOARD)
            self.gpio.setup(self.pwr_pin, self.gpio.OUT)  
            self.gpio.output(self.pwr_pin,self.gpio.HIGH)        
            
    def __del__(self):
        # close serial port on destruction of object
        self.port.close()
        
        #clear Gpio pins if used
        if self.dtr_pin != 0:
            self.gpio.cleanup(self.dtr_pin)
        if self.pwr_pin != 0:
            self.gpio.cleanup(self.pwr_pin)
        
    def __repr__(self):
        return str(self.gps_read())
        
    def power(self, on=True, attempts=3):
        for i in range(attempts):
            if on:
                if self.standby(0,attempts=1):
                    return True
                else:
                    self.power_toggle()
                    if self.standby(0,attempts=attempts):
                        return True
                    else:
                        continue
            else:
                self.port.write(b'AT+CPOWD=1\r\n')
                self.port.write(b'AT+CCID\r\n')
                failed = False
                for i in range(attempts*3):
                    if self.port.readline() != b'':
                        failed  = True
                        break
                if failed:
                    continue
                else:
                    return True
        return False
        
    def power_toggle(self,duration=3):
        if self.pwr_pin != 0:
            self.gpio.output(self.pwr_pin,self.gpio.LOW)
            time.sleep(duration)
            self.gpio.output(self.pwr_pin,self.gpio.HIGH)
            return True
        return False
    
    # 0 = slow clock off, 1 = slow clock on, 2 = slow clock auto
    # dtr pin needs to be connected and initialized for manual options
    def standby(self,stby=1, attempts=3):
        for i in range(attempts):
            if stby == 1:
                if self.dtr_pin == 0:
                    return False
                self.gpio.output(self.dtr_pin,self.gpio.HIGH)
                if not self.write_simple_command('AT+CSCLK=1',attempts):
                    continue
                return True
            if stby == 0:
                if self.dtr_pin == 0:
                    return False
                self.gpio.output(self.dtr_pin,self.gpio.LOW)
                self.port.write(b'AT+CSCLK=0\r\n')
                time.sleep(3)
                self.port.write(b'AT+CCID\r\n')
                for i in range(attempts*3):
                    line = self.port.readline() 
                    if line != b'' and line != b'AT+CSCLK=0\r\n' and line != b'AT+CCID\r\n':
                        return True
                continue
            if stby == 2:
                if not self.write_simple_command('AT+CSCLK=2',attempts):
                    continue
                return True
        return False
    
    # extract file name from full path    
    def get_file_from_path(self,path):
        pattern=re.compile('.*/(.*\..*$)')
        m = pattern.match(path)
        if m:
            return m.group(1)
        return path
        
    # available types: "REC UNREAD", "REC READ", "STO UNSENT", "STO SENT", "ALL"
    # mode: 0=normal, 1=don't change status of record
    def sms_get(self, type='ALL', mode=0, attempts=3):
        for i in range(attempts):
            # set SMS Text Mode (1= txt, 0 = PDU)
            if not self.write_simple_command('AT+CMGF=1'):
                continue
            pattern = re.compile('[+]CMGL: (\d),"(.*)","(.*)","(.*)","(.*)"\\r\\n')

            self.port.write('AT+CMGL="{}",{}\r\n'.format(type,mode).encode('utf-8'))
            for j in range(25):
                line = self.port.readline()
                if line == 'AT+CMGL="{}",{}\r\r\n'.format(type,mode).encode('utf-8'):
                    messages = []
                    for i in range(150):
                        try:
                            line = self.port.readline().decode('utf-8')
                        except:
                            continue
                        if line == 'OK\r\n':
                            return messages
                        m = pattern.match(line)
                        if m:
                            index = m.group(1)
                            stat = m.group(2)
                            sender = m.group(3)
                            alpha = m.group(4)
                            timestamp = m.group(5)
                            try:
                                line = self.port.readline()
                                message = line.decode('utf-8')
                            except Exception as e:
                                message = "Decoding error"
                            message = message.strip('\r\n')
                            messages.append({'index':index,'stat':stat,'sender':sender,'alpha':alpha,'timestamp':timestamp,'message':message})
                            self.port.readline()
                    return messages
        return None
     
    # mode:
    # 0 Delete the message specified in <index>
    # 1 Delete all read messages from preferred message storage, leaving unread messages and stored mobile originated
    #   messages (whether sent or not) untouched
    # 2 Delete all read messages from preferred message storage and sent mobile originated messages, leaving unread
    #   messages and unsent mobile originated messages untouched
    # 3 Delete all read messages from preferred message storage, sent and unsent mobile originated messages leaving unread messages untouched
    # 4 Delete all messages from preferred message storage including unread messages
    def sms_delete(self,index,mode=0,attempts=10):
        cmd = 'AT+CMGD={},{}'.format(index,mode)
        return self.write_simple_command(cmd)
    
    def sms_send(self, number, message, attempts=3):
        for i in range(attempts):
            # set SMS Text Mode (1= txt, 0 = PDU)
            if not self.write_simple_command('AT+CMGF=1'):
                continue
            
            # recipient number
            cmd = 'AT+CMGS=\"{}\"\r\n'.format(number)
            self.port.write(cmd.encode('utf-8'))
            try:
                line = self.port.readline().decode('utf-8')
            except:
                continue
            if line != 'AT+CMGS="{}"\r\r\n'.format(number):
                continue
            
            # message content
            self.port.write(message.encode('utf-8'))
            try:
                line = self.port.readline()
            except:
                continue
            if line != '> {}'.format(message).encode('utf-8'):
                continue
            
            # confirmation
            self.port.write(chr(26).encode('utf-8'))
            self.port.write('\r\n'.encode('utf-8'))
            for i in range(25):
                if self.port.readline() == b'OK\r\n':
                    return True
        return False
    
    def gps_activate(self,on=True):
        if on:
            return self.write_simple_command('AT+CGNSPWR=1')
        else:
            return self.write_simple_command('AT+CGNSPWR=0')
    
    def gps_timestamp_to_dict(self,stamp):
        return {'year':int(stamp[0:4]),'month':int(stamp[4:6]),'day':int(stamp[6:8]),
                'hour':int(stamp[8:10]),'minute':int(stamp[10:12]),'second':float(stamp[12:14])}
    
    def gps_read(self,attempts=3):
        for i in range(attempts):
            self.port.write('AT+CGNSINF\r\n'.encode('utf-8'))
            labels = ['GPSon','GPSfix','UTC','Lat','Long','MSLalt','Speed','Course','FixMode','Res1',
            'HDOP','PDOP','VDOP','Res2','GPSsatView','GPSsatUsed','GLONASSsatView','Res3','C/N0max','HPA','VPA']
            integers = [0,1,8,14,15,16,18]
            floats = [2,3,4,5,6,7,10,11,12,19,20]
            
            line = self.port.readline()
            raw_gps = []
            gps = {}
            if line == b'AT+CGNSINF\r\r\n':
                for i in range(10):
                    try:
                        line = self.port.readline().decode('utf-8')
                    except:
                        continue
                    if line == 'OK\r\n':
                        return gps
                    raw_gps = line[10:-2].split(',')
                    for i in range(len(raw_gps)):
                        if i in integers:
                            try:
                                gps[labels[i]] = int(raw_gps[i])
                            except:
                                gps[labels[i]] = raw_gps[i]
                        elif i in floats:
                            try:
                                gps[labels[i]] = float(raw_gps[i])
                            except:
                                gps[labels[i]] = raw_gps[i]
                        else:
                            gps[labels[i]] = raw_gps[i]
                    gps['UTCdict']=self.gps_timestamp_to_dict(str(gps['UTC']))
                    return gps
        return None
    
    # write a simple command that is replied to with OK
    def write_simple_command(self, cmd, attempts=3):
        cmd = (cmd+"\r\n").encode('utf-8')
        #print(cmd)
        for i in range(attempts):
            self.port.reset_input_buffer()
            self.port.reset_output_buffer()
            self.port.write(cmd)
            for j in range(attempts*2):
                line = self.port.readline()
                #print(line)
                if line == b'OK\r\n':
                    #print("Command {} sent successfully.".format(cmd[:-2]))
                    return True
        print("Couldn't send command {}.".format(cmd[:-2]))
        return False
    
    
    def ftp_parameters(self, apn, server, port, user, pwd):
        self.apn = apn
        self.ftp_server = server
        self.ftp_port = port
        self.ftp_user = user
        self.ftp_pwd = pwd
    
    def ftp_initialize(self, attempts=5):
        print('Setting up FTP connection.')
        for i in range(attempts):
            if not self.bearer_set_connection_type(bearer=1, type="GPRS",attempts=attempts):
                continue
            if not self.bearer_set_apn(bearer=1, apn=self.apn,attempts=attempts):
                continue
            if not self.bearer_open(bearer=1,attempts=attempts):
                continue
            if not self.ftp_set_profile_id(1,attempts=attempts):
                continue
            if not self.ftp_set_server(self.ftp_server,attempts=attempts):
                continue
            if not self.ftp_set_port(self.ftp_port,attempts=attempts):
                continue
            if not self.ftp_set_username(self.ftp_user,attempts=attempts):
                continue
            if not self.ftp_set_password(self.ftp_pwd,attempts=attempts):
                continue
            return True
        return False
        
    def email_send(self,subject,message,recipient_to_address,recipient_to_name,recipient_cc_address='',
                    recipient_cc_name='',recipient_bcc_address='',recipient_bcc_name='',attachment='',attempts=3):
        smtp_errors = {61:'Network error',62:'DNS resolve error',63:'SMTP TCP connection error',64:'Timeout of SMTP server response',
                        65:'SMTP server response error',66:'No authentication',68:'Bad recipient',
                        67:'Authentication failed. SMTP user name or password maybe not right.'}
        for i in range(attempts):
            message = message.encode('utf-8').hex()
            if not self.email_set_recipient('to',recipient_to_address,recipient_to_name,attempts):
                continue
            if not self.email_set_subject(subject,attempts):
                continue
            self.port.write('AT+SMTPBODY={}\r\n'.format(len(message)).encode('utf-8'))
            for j in range(5):
                line = self.port.readline()
                if line == b'DOWNLOAD\r\n':
                    self.port.write(message.encode('utf-8'))
                    break
            for j in range(15):
                line = self.port.readline()
                if line == b'OK\r\n':
                    break
            self.port.write('AT+SMTPSEND\r\n'.encode('utf-8'))
            for j in range(35):
                line = self.port.readline()
                #print(line)
                if line == b'+SMTPSEND: 1\r\n':
                    print('Email sent to {}.'.format(recipient_to_name))
                    return True
                elif b'+SMTPSEND:' in line:
                    line = line.decode('utf-8')
                    pattern = re.compile('[+]SMTPSEND: (\d+)\\r\\n')
                    m = pattern.matchz(line)
                    error = int(match.group(1))
                    error = smtp_errors[error]
                    print('Error sending Email: {}.'.format(error))
                    return False

            return False
    
    def email_parameters(self,apn,server,port,user,pwd,sender_address,sender_name,ssl=0,timeout=30,charset='UTF-8'):
        self.apn = apn
        self.email_timeout = timeout
        self.email_charset = charset
        self.email_server = server
        self.email_port = port
        self.email_user = user
        self.email_pwd = pwd
        self.email_sender_address = sender_address
        self.email_sender_name = sender_name
        self.email_ssl = ssl

    def email_initialize(self, attempts=5):
        for i in range(attempts):
            print('Setting up SMTP connection.')
            if not self.bearer_set_connection_type(bearer=1, type="GPRS",attempts=attempts):
                continue
            if not self.bearer_set_apn(bearer=1, apn=self.apn,attempts=attempts):
                continue
            if not self.bearer_open(bearer=1,attempts=attempts):
                continue
            if not self.email_set_profile_id(1,attempts=attempts):
                continue
            if not self.email_set_timeout(self.email_timeout,attempts=attempts):
                continue
            if not self.email_set_charset(self.email_charset,attempts=attempts):
                continue
            if not self.email_set_server(self.email_server,self.email_port,attempts=attempts):
                continue
            if not self.email_set_auth(self.email_user,self.email_pwd,attempts=attempts):
                continue
            if not self.email_set_sender(self.email_sender_address,self.email_sender_name,attempts=attempts):
                continue
            if not self.email_set_ssl(self.email_ssl,attempts=attempts):
                continue
            return True
        return False
    
    # 0 Not use encrypted transmission 
    # 1 Begin encrypt transmission with encryption port 
    # 2 Begin encrypt transmission with normal port
    def email_set_ssl(self, ssl, attempts=3):
        cmd = 'AT+EMAILSSL={}'.format(ssl)
        return self.write_simple_command(cmd, attempts)
    
    def email_set_subject(self, subject, attempts=3):
        cmd = 'AT+SMTPSUB="{}"'.format(subject.encode('utf-8').hex())
        return self.write_simple_command(cmd, attempts)
    
    def email_set_charset(self, charset, attempts=3):
        cmd = 'AT+SMTPCS="{}"'.format(charset)
        return self.write_simple_command(cmd, attempts)
    
    def email_set_timeout(self, timeout, attempts=3):
        cmd = 'AT+EMAILTO={}'.format(timeout)
        return self.write_simple_command(cmd, attempts)
        
    def email_set_recipient(self,type,  recipient_address, recipient_name, attempts=3):
        types = {'to':0,'cc':1,'bcc':2}
        cmd = 'AT+SMTPRCPT={},0,"{}","{}"'.format(types[type],recipient_address,recipient_name)
        return self.write_simple_command(cmd, attempts)
        
    def email_set_sender(self, sender_address, sender_name, attempts=3):
        cmd = 'AT+SMTPFROM="{}","{}"'.format(sender_address,sender_name)
        return self.write_simple_command(cmd, attempts)
        
    def email_set_auth(self, user, pwd, attempts=3):
        cmd = 'AT+SMTPAUTH=1,"{}","{}"'.format(user,pwd)
        return self.write_simple_command(cmd, attempts)
    
    def email_set_profile_id(self, id, attempts=3):
        cmd = 'AT+EMAILCID={}'.format(id)
        return self.write_simple_command(cmd, attempts)
        
    def email_set_server(self, server, port, attempts=3):
        cmd = 'AT+SMTPSRV="{}",{}'.format(server,port)
        return self.write_simple_command(cmd, attempts)
        
    def clock_network_sync(self, on=1, attempts=3):
        cmd = 'AT+CLTS={};&W'.format(on)
        return self.write_simple_command(cmd, attempts)

    # 0 = no flowcontrol, 1= software flowcontrol, 2 = hardware flowcontrol
    def flowcontrol_set(self,fc=0,attempts=3):
        cmd = 'AT+IFC={},{}'.format(fc,fc)
        return self.write_simple_command(cmd,attempts=attempts)
    
    def ftp_set_username(self, user, attempts=3):
        cmd = 'AT+FTPUN="{}"'.format(user)
        return self.write_simple_command(cmd, attempts)
        
    def ftp_set_password(self, pwd, attempts=3):
        cmd = 'AT+FTPPW="{}"'.format(pwd)
        return self.write_simple_command(cmd, attempts)
        
    def ftp_set_port(self, port, attempts=3):
        cmd = 'AT+FTPPORT={}'.format(port)
        return self.write_simple_command(cmd, attempts)
        
    def ftp_set_server(self, server, attempts=3):
        cmd = 'AT+FTPSERV="{}"'.format(server)
        return self.write_simple_command(cmd, attempts)
        
    def ftp_put_name(self, name, attempts=3):
        cmd = 'AT+FTPPUTNAME="{}"'.format(name)
        return self.write_simple_command(cmd, attempts)
        
    def ftp_put_path(self, path, attempts=3):
        cmd = 'AT+FTPPUTPATH="{}"'.format(path)
        return self.write_simple_command(cmd, attempts)
        
    def ftp_get_name(self, name, attempts=3):
        cmd = 'AT+FTPGETNAME="{}"'.format(name)
        return self.write_simple_command(cmd, attempts)
        
    def ftp_get_path(self, path, attempts=3):
        cmd = 'AT+FTPGETPATH="{}"'.format(path)
        return self.write_simple_command(cmd, attempts)
        
    def ftp_set_profile_id(self, id, attempts=3):
        cmd = 'AT+FTPCID={}'.format(id)
        return self.write_simple_command(cmd, attempts)
        
    def ftp_quit(self, attempts=3):
        return self.write_simple_command('AT+FTPQUIT', attempts)
        
    def bearer_set_connection_type(self, bearer=1, type="GPRS", attempts=3):
        cmd = 'AT+SAPBR=3,{},"Contype","{}"'.format(bearer,type)
        return self.write_simple_command(cmd, attempts)
        
    def bearer_set_apn(self, apn, bearer=1, attempts=3):
        cmd = 'AT+SAPBR=3,{},"APN","{}"'.format(bearer,apn)
        return self.write_simple_command(cmd, attempts)
        
    def bearer_open(self, bearer=1, attempts=5):
        status = self.bearer_get_status(bearer=bearer)
        if status in (0,2):
            time.sleep(2)
            return self.bearer_open(bearer=bearer)
        elif status == 1:
            return True
        else:
            cmd = 'AT+SAPBR=1,{}'.format(bearer)
            self.write_simple_command(cmd)
            if attempts >= 0:
                return self.bearer_open(bearer=bearer,attempts=attempts-1)
            else:
                return False
        
    def bearer_close(self, bearer=1, attempts=5):
        status = self.bearer_get_status(bearer=bearer)
        if status in (0,2):
            time.sleep(2)
            return self.bearer_close(bearer=bearer)
        elif status == 3:
            return True
        else:
            cmd = 'AT+SAPBR=0,{}'.format(bearer)
            self.write_simple_command(cmd)
            if attempts >= 0:
                return self.bearer_close(bearer=bearer,attempts=attempts-1)
            else:
                return False
        
    def bearer_query(self, bearer=1, attempts=3):
        for i in range(attempts):
            self.port.reset_input_buffer()
            self.port.reset_output_buffer()
            self.port.write('AT+SAPBR=2,1\r\n'.encode('utf-8'))
            pattern=re.compile('[+]SAPBR: (\d),(\d),"(\d+\.\d+\.\d+\.\d+)"\\r\\n')
            for j in range(5):
                try:
                    line = self.port.readline().decode('utf-8')
                except:
                    continue
                m = pattern.match(line)
                if  m != None:
                    cid = int(m.group(1))
                    status = int(m.group(2))
                    ip = m.group(3)
                    return cid, status, ip
        return 0, 0, ""
    
    # 0 = connecting, 1 = connected, 2 = closing, 3 = closed
    def bearer_get_status(self, bearer=1):
        cid, status, ip = self.bearer_query(bearer = bearer)
        return status
            
    def bearer_get_ip(self, bearer=1):
        cid, status, ip = self.bearer_query(bearer = bearer)
        return ip
    
    # opening a ftp put session returns either an error or a maximum length for transfer
    def ftp_open_put_session(self,attempts=3):
        if not self.write_simple_command('AT+FTPPUT=1',attempts=attempts):
            return (False,0,0)
        pattern = re.compile('[+]FTPPUT: (\d),(\d+),?(\d+)?')
        for i in range(50):
            try:
                line = self.port.readline().decode('utf-8')
            except:
                continue
            if not 'FTPPUT' in line:
                continue
            m = pattern.match(line)
            if m:
                mode = int(m.group(1))
                if mode != 1:
                    return (False,0,0)
                error = int(m.group(2))
                if error != 1:
                    return (False,error,0)
                else:
                    maxlength = int(m.group(3))
                    return (True, 1, maxlength)
            else:
                return self.open_put_session()
    
    def ftp_close_put_session(self,attempts=3):
        return self.write_simple_command('AT+FTPPUT=2,0', attempts)
        
    def ftp_file_delete(self,file,dir,attempts=3):
        for i in range(attempts):
            print('Deleting file.')
            if not self.ftp_get_name(file,attempts=attempts):
                continue
            if not self.ftp_get_path(dir,attempts=attempts):
                continue
            if not self.write_simple_command('AT+FTPDELE') :
                continue
            for i in range(20):
                line = self.port.readline()
                if line == b'+FTPDELE: 1,0\r\n':
                    print('Deleted {}.'.format(file))
                    return True
        print('Could not delete {}.'.format(file))
        return False
    
    # if file is smaller than the max transfer length, it can be transferred as one chunk
    # this function is not for direct use, file transfers including setup are implemented in ftp_file_upload
    def ftp_put_file_small(self,data,attempts=3):
        for i in range(attempts):
            self.port.write('AT+FTPPUT=2,{}\r\n'.format(len(data)).encode('utf-8'))
            for j in range(5):
                raw_line = self.port.readline()
                try:
                    line = raw_line.decode('utf-8')
                except:
                    continue
                if line == 'AT+FTPPUT=2,{}\r\r\n'.format(len(data)):
                    raw_line = self.port.readline()
                    try:
                        line = raw_line.decode('utf-8')
                    except:
                        continue
                    if line == '+FTPPUT: 2,{}\r\n'.format(len(data)):
                        self.port.write(data)
                        for k in range(30):
                            line = self.port.readline()
                            if line == b'OK\r\n':
                                return True
                            elif line == b'ERROR\r\n':
                                #print('\nError\n')
                                return False
        return False
        
    # this function is not for direct use, file transfers including setup are implemented in ftp_file_upload
    def ftp_put_file_large(self,data,maxlength,attempts=3):
        size = len(data)
        pointer=0
        pattern = re.compile('[+]FTPPUT: (\d),(\d+),?(\d+)?.*')
        errors = 0
        for i in range(attempts):
            while True:
                chunk = data[pointer:(pointer+maxlength)]
                chunk_size = len(chunk)
                if not self.ftp_put_file_small(chunk,attempts=attempts):
                    errors = errors+1
                    for j in range(50):
                        try:
                            raw_line = self.port.readline()
                            line = raw_line.decode('utf-8')
                        except:
                            continue
                        m = pattern.match(line)
                        if m:
                            mode = int(m.group(1))
                            error = int(m.group(2))
                            if mode == 1 and error == 1:
                                new_maxlength = int(m.group(3))
                                maxlength=new_maxlength
                                break
                    continue
                if chunk_size+1 < maxlength:
                    print('Transferred {} of {} bytes ({} package errors).                       '.format(pointer+chunk_size,size,errors), end='\n')
                    return True
                for j in range(50):
                    try:
                        raw_line = self.port.readline()
                        line = raw_line.decode('utf-8')
                    except:
                        continue
                    m = pattern.match(line)
                    if m:
                        #print('\n',raw_line)
                        mode = int(m.group(1))
                        error = int(m.group(2))
                        if mode == 1 and error == 1:
                            new_maxlength = int(m.group(3))
                            pointer = pointer+maxlength
                            maxlength=new_maxlength
                            break
                print('Transferred {} of {} bytes ({} package errors).          '.format(pointer+chunk_size, size, errors), end='\r')
        return False
    
    # if validate = True, the correct file size on the FTP server is confirmed after the transfer 
    def ftp_file_upload(self,file,dir,validate=False,attempts=3):
        start_time = time.time()
        for i in range(attempts):
            # if any step fails, stop and restart procedure
            file_name = self.get_file_from_path(file)
            if not self.ftp_put_name(file_name):
                continue
            if not self.ftp_put_path(dir):
                continue
            print('\nOpening FTP Put Session.')
            ftp_open, ftp_error, ftp_maxlength = self.ftp_open_put_session()
            if not ftp_open:
                self.ftp_initialize()
                print(self.ftp_errors[ftp_error])
                continue
            f = open(file,'rb')
            f_data=f.read()
            f.close()
            if len(f_data) < ftp_maxlength:
                print('small file')
                if not self.ftp_put_file_small(f_data,ftp_maxlength):
                    continue
                print('Transferred {} bytes.'.format(len(f_data)))
            else:
                if not self.ftp_put_file_large(f_data,ftp_maxlength):
                    continue
            self.ftp_close_put_session()  
            duration = time.time()-start_time
            speed = int(len(f_data)/duration)
            print('Transfer of {} completed in {:.2f} seconds ({} B/s).'.format(file, duration, speed))
            
            if validate:
                if len(f_data) == self.ftp_get_filesize(dir,file,attempts=attempts):
                    print("File size validated.")
                    return True
                else:
                    print("File size does not match, attempt again:")
                    self.ftp_file_delete(file,dir,attempts=attempts)
                    continue
            else:
                return True
        print('Transfer of {} failed.'.format(file))
        return False
    
    # local directory has to already exist or be created separately
    def ftp_file_download(self,file,dir_server,dir_local='',validate=False,attempts=3):
        
        data = b'' 
        chunk = b''
        error = False
        errors = []
        download_open = False
        download_complete = False
        output = {}
        file_start = time.time()
        
        for i in range(attempts):
            if not self.ftp_get_name(file,attempts=attempts):
                continue
            if not self.ftp_get_path(dir_server,attempts=attempts):
                continue
            if not self.write_simple_command('AT+FTPREST=0',attempts=attempts):
                continue
                
            if error:
                self.write_simple_command('AT+FTPREST={}'.format(len(data)-len(chunk)),attempts=attempts)
                data = data[:-len(chunk)]
                error = False
            
            if not self.write_simple_command('AT+FTPGET=1',attempts=attempts):
                continue
                        
            for j in range(75):
                try:
                    line = self.port.readline().decode('utf-8')
                    #print(line)
                except:
                    continue
                if line == '+FTPGET: 1,1\r\n':
                    download_open = True
                    break
                if line == '+FTPGET: 1,0\r\n':
                    download_complete = True
                    break
                if '+FTPGET: 1,' in line:
                    pattern = re.compile('[+]FTPGET: 1,(\d+)\\r\\n')
                    m = pattern.match(line)
                    error = int(m.group(1))
                    errors.append(error)
                    error = True
                    break
                    
            if error:
                continue
            if download_complete:
                duration = time.time()-file_start
                size = len(data)
                speed = int(size/duration)
                print('\nDownloaded {} in {:.1f} seconds({} bytes, {} B/s)'.format(file,duration,size,speed))
                
                if validate:
                    if len(data) == self.ftp_get_filesize(dir_server,file):
                        print('File size validated.')
                    else:
                        print('File size incorrect, attempt again.')
                        error = True
                        continue
                        
                output['errors'] = errors
                output['data'] = data
                output['complete'] = True
                try:
                    path = dir_local + file
                    f = open(path,'wb')
                    f.write(data)
                    f.close()
                except Exception as e:
                    print('Could not write data to file.', e)
                return output
                
            if download_open:
                print('\nStarting download.')
                j = 0
                while j < 75:
                    j = j+1 
                    chunk_start = time.time()
                    self.port.write('AT+FTPGET=2,1024\r\n'.encode('utf-8'))
                    for k in range(100):
                        try:
                            line = self.port.readline().decode('utf-8')
                            #print('1',line)
                        except:
                            continue
                        if line == '+FTPGET: 2,0\r\n':
                            #print('No data.')
                            break
                        if line == 'ERROR\r\n':
                            error = True
                            break
                        if '+FTPGET: 2,' in line:
                            pattern = re.compile('[+]FTPGET: 2,(\d+)\\r\\n')
                            m = pattern.match(line)
                            length = int(m.group(1))
                            chunk = self.port.read(length)
                            data = data + chunk
                            print('Downloaded {} bytes ({} package errors).'.format(len(data),len(errors)), end='\r')
                            j = 0
                            break
                        if line == '+FTPGET: 1,0\r\n':
                            download_complete = True
                            break
                        if line == '+FTPGET: 1,1\r\n':
                            download_open = True
                        if '+FTPGET: 1,' in line:
                            pattern = re.compile('[+]FTPGET: 1,(\d+)\\r\\n')
                            m = pattern.match(line)
                            error = int(m.group(1))
                            errors.append(error)
                            error = True
                            break
                            
                    if error:
                        break
                        
                    if download_complete:
                        duration = time.time()-file_start
                        size = len(data)
                        speed = int(size/duration)
                        print('\nDownloaded {} in {:.1f} seconds({} bytes, {} B/s)'.format(file,duration,size,speed))
                        if validate:
                            if len(data) == self.ftp_get_filesize(dir_server,file):
                                print('File size validated.')
                            else:
                                print('File size incorrect, attempt again.')
                                error = True
                                break
                        output['errors'] = errors
                        output['data'] = data
                        output['complete'] = True
                        try:
                            path = dir_local + file
                            f = open(path,'wb')
                            f.write(data)
                            f.close()
                        except Exception as e:
                            print('Could not write data to file.', e)
                        return output
                        
                    if download_open:
                        j = 0
                        continue
            if error:
                continue
        
        # return whatever was downloaded when attempts timed out      
        output['errors'] = errors
        output['data'] = data
        output['complete'] = False
        
        duration = time.time()-file_start
        size = len(data)
        speed = int(size/duration)
        print('\nDownload of {} interrupted after {:.1f} seconds({} bytes, {} B/s)'.format(file,duration,size,speed))
        try:
            path = dir_local + file
            f = open(path,'wb')
            f.write(data)
            f.close()
        except Exception as e:
            print('Could not write data to file.', e)
        return output
     
    # create = True for making dir, False for deleting dir     
    def ftp_dir_create_delete(self, dir, create, attempts=3):
        for i in range(attempts):
        # if any step fails, stop and restart procedure
            if not self.ftp_get_path(dir):
                continue
            if create:
                print('Creating directory {}.'.format(dir))
                if not self.write_simple_command('AT+FTPMKD'):
                    continue
                pattern = re.compile('[+]FTPMKD: \d,(\d+)\\r\\n')
                for j in range(15):
                    try:
                        line = self.port.readline().decode('utf-8')
                    except:
                        continue
                    m = pattern.match(line)
                    if m:
                        ftp_error = int(m.group(1))
                        if ftp_error == 0:
                            return True
                        else:
                            print(self.ftp_errors[ftp_error])
                            return False
                    else:
                        continue
            else:
                print('Removing directory {}.'.format(dir))
                if not self.write_simple_command('AT+FTPRMD'):
                    continue
                pattern = re.compile('[+]FTPRMD: \d,(\d+)\\r\\n')
                for j in range(15):
                    try:
                        line = self.port.readline().decode('utf-8')
                    except:
                        continue
                    m = pattern.match(line)
                    if m:
                        ftp_error = int(m.group(1))
                        if ftp_error == 0:
                            return True
                        else:
                            print(self.ftp_errors[ftp_error])
                            return False
                    else:
                        continue
        return False
        
    def ftp_get_filesize(self,dir,file,attempts=3):
        for i in range(attempts):
            if not self.ftp_get_path(dir,attempts=attempts):
                continue
            if not self.ftp_get_name(file,attempts=attempts):
                continue
            if not self.write_simple_command('AT+FTPSIZE\r\n',attempts=attempts):
                continue
            for i in range(attempts*10):
                line = self.port.readline()
                try:
                    line = line.decode('utf-8')
                except:
                    continue
                if '+FTPSIZE: 1,0,' in line:
                    pattern = re.compile('[+]FTPSIZE: 1,0,(\d+)\\r\\n')
                    m = pattern.match(line)
                    if m:
                        return int(m.group(1))
                    else:
                        return 0
                elif '+FTPSIZE: 1,' in line:
                    pattern = re.compile('[+]FTPSIZE: 1,(\d+).*')
                    m = pattern.match(line)
                    error = int(m.group(1))
                    print('Error',self.ftp_errors(error))
                    return 0
        return 0
        
    def ftp_list_decode(self,list,encoding,error=False):
        output = {}
        output['error'] = error
        pattern = re.compile(encoding[0])
        labels = encoding[1]
        if 'type' in labels:
            output['elements'] = {}
            output['decoding_errors'] = []
            types = []
            for element in list:
                m = pattern.match(element)
                if m:
                    type = m.group(labels.index('type')+1)
                    if type not in types:
                        types.append(type)
            for type in types:
                output['elements'][type]=[]
            for element in list:
                dict = {}
                m = pattern.match(element)
                if m:
                    for i in range(len(labels)):
                         dict[labels[i]] = m.group(i+1)
                    type = m.group(labels.index('type')+1)
                    output['elements'][type].append(dict)
                else:
                    output['decoding_errors'].append(element)
                    
        else:
            output['elements'] = []
            output['decoding_errors'] = []
            for element in list:
                dict = {}
                m = pattern.match(element)
                if m:
                    for i in range(len(labels)):
                        dict[labels[i]] = m.group(i+1)
                    output['elements'].append(dict)  
                else:
                    output['decoding_errors'].append(element)
        return output
    
    # encoding of list can vary between ftp servers
    # common seems to be: ['([\w-]+)\s+(\d+)\s+(\w+)\s+(\w+)\s+(\d+)\s+(.+\s+.+\s+.+)\s+(.+)',['permissions','type','user','group','size','date/time','name']]
    # encoding = [] gives raw list
    # otherwise specify as [<regex pattern>,[<label0>,<label1>,...]]
    def ftp_list_dir(self, dir, encoding=[],attempts=3):
        for i in range(attempts):
            error = False
            transfer_complete = False
            # set directory
            if not self.ftp_get_path(dir):
                continue
            # start ftp list session   
            print('Opening FTP directory readout.')
            if not self.write_simple_command('AT+FTPLIST=1'):
                continue
            
            start = time.time()            
            # using while loop to be able to reset counter
            j=0
            dir_list = b''
            while j < 50:
                j = j+1
                try:
                    line = self.port.readline().decode('utf-8')
                    #print('3',line)
                except:
                    continue
                if line == '+FTPLIST: 1,0\r\n' or transfer_complete:
                    # data transfer finished
                    print('Data transfer complete.')
                    if encoding == []:
                        return dir_list.decode('utf-8').split('\r\n')
                    else:
                        return self.ftp_list_decode(dir_list.decode('utf-8').split('\r\n'),encoding)
                if line == b'ERROR\r\n':
                    error = True
                if '+FTPLIST: 2,' in line:
                    # data transmission is beginning
                    # get size of data and read that many bytes
                    pattern = re.compile('[+]FTPLIST: 2,(\d+)\\r\\n')
                    m = pattern.match(line)
                    size = m.group(1)
                    chunk = self.port.read(int(size))
                    #print(chunk)
                    dir_list = dir_list + chunk
                    # transmission of data block completed
                    continue
                elif line == '+FTPLIST: 1,1\r\n':
                    print('Receiving Data.')
                    # ftp list session is open
                    
                    no_data = False
                    k = 0
                    while k <10:
                        k = k+1
                        # request data
                        self.port.write('AT+FTPLIST=2,1460\r\n'.encode('utf-8'))
                        
                        for l in range(attempts):
                            try:
                                line = self.port.readline().decode('utf-8')
                                #print('1',line)
                            except:
                                continue
                            if line == b'ERROR\r\n':
                                error = True
                                break
                            if line == '+FTPLIST: 1,0\r\n':
                                transfer_complete = True
                                break
                            if line == '+FTPLIST: 2,0\r\n':
                                no_data = True
                                for i in range(20):
                                    try:
                                        line = self.port.readline().decode('utf-8')
                                        #print('2',line)
                                    except:
                                        continue
                                    if line == 'OK\r\n':
                                        #print('Okidoki')
                                        j=0
                                        break
                                break
                            elif '+FTPLIST: 2,' in line:
                                # data transmission is beginning
                                # get size of data and read that many bytes
                                pattern = re.compile('[+]FTPLIST: 2,(\d+)\\r\\n')
                                m = pattern.match(line)
                                size = m.group(1)
                                chunk = self.port.read(int(size))
                                #print(chunk)
                                dir_list = dir_list + chunk
                                block_finished = True
                                k=0
                                # transmission of data block completed
                                break
                        if transfer_complete or error:
                            break
                elif error:
                    continue
                        
                elif '+FTPLIST: 1,' in line:
                    print(line)
                    # error
                    pattern = re.compile('[+]FTPLIST: 1,(\d+)\\r\\n')
                    m = pattern.match(line)
                    error = int(m.group(1))
                    print('FTP Error:',self.ftp_errors[error])
                    print(time.time()-start)
                    
                    if encoding == []:
                        return dir_list.decode('utf-8').split('\r\n')
                    else:
                        return self.ftp_list_decode(dir_list.decode('utf-8').split('\r\n'),encoding,error=True)
            return[]
    
        # get ccid of sim card (0 = error)
    def sim_get_ccid(self, attempts=3):
        for i in range(attempts):
            self.port.write('AT+CCID\r\n'.encode('utf-8'))
            pattern = re.compile('(.*)\r\n')
            for j in range(5):
                try:
                    line = self.port.readline().decode('utf-8')
                except:
                    continue
                if line == 'AT+CCID\r\r\n':
                    try:
                        line = self.port.readline().decode('utf-8')
                    except:
                        continue
                    m = pattern.match(line)
                    if m:
                        ccid = m.group(1)
                        return ccid
        return 0
    
    # lac & ci (location infor only returned when n=2, stat: 
    # 0 Not registered, MT is not currently searching a new operator to register to
    # 1 Registered, home network
    # 2 Not registered, but MT is currently searching a new operator to register to
    # 3 Registration denied
    # 4 Unknown
    # 5 Registered, roaming
    def network_get_registration(self, attempts=3):
        for i in range(attempts):
            self.port.write('AT+CREG?\r\n'.encode('utf-8'))
            pattern = re.compile('[+]CREG: (\d),(\d),?(".+")?,?(".+")?\\r\\n')
            for j in range(5):
                try:
                    line = self.port.readline().decode('utf-8')
                except:
                    continue
                m = pattern.match(line)
                if m:
                    n = int(m.group(1))
                    stat = int(m.group(2))
                    lac = m.group(3)
                    ci = m.group(4)
                    return {'n':n, 'stat':stat, 'lac':lac, 'ci':ci}
        return {'n':None, 'stat':None, 'lac':None, 'ci':None}
    
    # get list of available network operators, first home network then networks referenced in SIM, and other networks.
    def operator_get_available(self, attempts=3):
        for i in range(attempts):
            self.port.write('AT+COPS=?\r\n'.encode('utf-8'))
            pattern = re.compile('[+]COPS: ([(].+[)]),,([(].+[)]),([(].+[)])\\r\\n')
            for j in range(20):
                try:
                    line = self.port.readline().decode('utf-8')
                except:
                    continue
                m = pattern.match(line)
                if m:
                    available_raw = m.group(1).split("),(")
                    available = []
                    for operator in available_raw:
                        operator = operator.strip("()").split(',')
                        operator_dict = {}
                        operator_dict['supported_stat'] = int(operator[0])
                        operator_dict['id_long'] = operator[1].strip('"')
                        operator_dict['id_short'] = operator[2].strip('"')
                        operator_dict['id_num'] = int(operator[3].strip('"'))
                        available.append(operator_dict)
                    modes = m.group(2)
                    formats = m.group(3)
                    return {'available':available,'modes':modes,'formats':formats}
        return {'available':None,'modes':None,'formats':None} 
        
    def operator_get_current(self, attempts=3):
        for i in range(attempts):
            self.port.write('AT+COPS?\r\n'.encode('utf-8'))
            pattern = re.compile('[+]COPS: (\d),?(\d)?,?(.*)?\\r\\n')
            for j in range(5):
                try:
                    line = self.port.readline().decode('utf-8')
                except:
                    continue
                if line == 'AT+COPS?\r\r\n':
                    try:
                        line = self.port.readline().decode('utf-8')
                    except:
                        continue
                    m = pattern.match(line)
                    if m:
                        mode = int(m.group(1))
                        if m.group(2):
                            format = m.group(2)
                            operator = m.group(3).strip('"')
                        else:
                            format = None
                            operator = None
                        current_operator = {'mode':mode,'format':format,'operator':operator}
                        return current_operator
        return {'mode':None,'format':None,'operator':None}
    
    def operator_set_automatic(self,attempts=3):
        cmd = 'AT+COPS=0'
        return self.write_simple_command(cmd,attempts=attempts)
        
    # Mode:
    # 0 Automatic mode; <oper> field is ignored
    # 1 Manual (<oper> field shall be present, and <AcT> optionally)
    # 2 manual deregister from network
    # 3 set only <format> (for read Command +COPS?) - not shown in Read Command response
    # 4 Manual/automatic (<oper> field shall be present); if manual selection fails, automatic mode (<mode>=0) is entered
    # Format:
    # 0 Long format alphanumeric <oper>
    # 1 Short format alphanumeric <oper>
    # 2 Numeric <oper>; GSM Location Area Identification
    def operator_set_manual(self, mode=1, format=0, operator="", attempts=3):
        cmd = 'AT+COPS={},{},"{}"'.format(mode,format,operator)
        return self.write_simple_command(cmd,attempts=attempts)
    
    # baudrate 0 = automatic mode
    def get_serial_baudrate(self,attempts=3):
        for i in range(attempts):
            self.port.write('AT+IPR?\r\n'.encode('utf-8'))
            pattern = re.compile('[+]IPR: (\d+)\\r\\n')
            for j in range(5):
                try:
                    line = self.port.readline().decode('utf-8')
                except:
                    continue
                if line == 'AT+IPR?\r\r\n':
                    try:
                        line = self.port.readline().decode('utf-8')
                    except:
                        continue
                    m = pattern.match(line)
                    if m:
                        baudrate = int(m.group(1))
                        return baudrate
        return None
    
    def set_serial_baudrate(self,baudrate=0,attempts=3):
        supported = [0,1200,2400,4900,9600,19200,38400,57600,115200,230400,460800]
        if baudrate in supported:
            cmd = 'AT+IPR={}'.format(baudrate)
            return self.write_simple_command(cmd,attempts=attempts)
        else:
            print('Baud rate not in supported({}).'.format(supported))
            return False

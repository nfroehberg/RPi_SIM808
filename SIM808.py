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
    sim.ftp_dir_create_delete('test_dir',True)
    # upload file
    sim.ftp_file_send(file="test_file.txt",dir="/test_dir/")

class SIM808():
    
    def __init__(self, port="/dev/ttyAMA0", baud=115200, t_out=1, rtscts=False, xonxoff=False):
        self.port = serial.Serial(port, baudrate=baud, timeout=t_out)
        self.ftp_errors = {1:'No Error',61:'Net Error',62:'DNS Error',63:'Connect Error',64:'Timeout',
                            65:'Server Error',66:'Operation not allowed', 70:'Replay Error',71:'User Error',
                            72:'Password Error',73:'Type Error',74:'Rest Error',75:'Passive error',
                            76:'Active error',77:'Operate Error',78:'Upload Error',79:'Download Error',
                            86:'Manual Quit'}
    def __del__(self):
        # close serial port on destruction of object
        self.port.close()
        
    def __repr__(self):
        return str(self.gps_read())
    
    def ftp_parameters(self, apn, server, port, user, pwd):
        self.apn = apn
        self.ftp_server = server
        self.ftp_port = port
        self.ftp_user = user
        self.ftp_pwd = pwd
    
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
        
    def ftp_initialize(self, attempts=5):
        print('Setting up FTP connection.')
        for i in range(attempts):
            if not self.bearer_set_connection_type(bearer=1, type="GPRS"):
                continue
            if not self.bearer_set_apn(bearer=1, apn=self.apn):
                continue
            if not self.bearer_open(bearer=1):
                continue
            if not self.ftp_set_profile_id(1):
                continue
            if not self.ftp_set_server(self.ftp_server):
                continue
            if not self.ftp_set_port(self.ftp_port):
                continue
            if not self.ftp_set_username(self.ftp_user):
                continue
            if not self.ftp_set_password(self.ftp_pwd):
                continue
            return True
        return False
            
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
    
    # if file is smaller than the max transfer length, it can be transferred as one chunk
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
        
    def ftp_put_file_large(self,data,maxlength,attempts=3):
        size = len(data)
        pointer=0
        pattern = re.compile('[+]FTPPUT: (\d),(\d+),?(\d+)?.*')
        errors = 0
        for i in range(attempts):
            while True:
                chunk_start_time = time.time()
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
                    print('Transferred {} of {} bytes ({} package errors).'.format(pointer+chunk_size,size,errors), end='\n')
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
                duration = time.time()-chunk_start_time
                speed = int(chunk_size/duration)
                print('Transferred {} of {} bytes ({} B/s, {} package errors).          '.format(pointer+chunk_size, size, speed,errors), end='\r')
        return False

    def ftp_file_send(self,file,dir,attempts=3):
        start_time = time.time()
        for i in range(attempts):
            # if any step fails, stop and restart procedure
            file_name = self.get_file_from_path(file)
            if not self.ftp_put_name(file_name):
                continue
            if not self.ftp_put_path(dir):
                continue
            print('Opening FTP Put Session.')
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
            return True
        print('Transfer of {} failed.'.format(file))
        return False
     
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
    
    # rssi 31 = best, 99 = error, rxqual 0 = best, 7 = worst, 99 = error
    def check_signal(self, attempts=3):
        for i in range(attempts):
            self.port.write('AT+CSQ\r\n'.encode('utf-8'))
            pattern = re.compile('[+]CSQ: (\d+),(\d+)\\r\\n')
            for j in range(5):
                try:
                    line = self.port.readline().decode('utf-8')
                except:
                    continue
                m = pattern.match(line)
                if m:
                    rssi = m.group(1)
                    rxqual = m.group(2)
                    return {'rssi':rssi, 'rxqual':rxqual}
        return {'rssi':99, 'rxqual':99}
    
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

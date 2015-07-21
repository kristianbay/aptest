import os
import sys
import time
import re
import string
import subprocess
import threading
import socket
import json
import optparse
import serial

def process_monitor(process, prefix):
    for line in process.stdout.readlines():
        print prefix + line

def serial_reader(prompt, output):
    """loop and copy serial->socket"""
    serial_port.write('\n')
    try:
        input_str = ''
        while True:
            data = serial_port.read(1)
            if data and len(data):
                #sys.stdout.write(str(json.dumps(data)))
                input_str += data
                sys.stdout.write(data)
                sys.stdout.flush()
                sock.sendall(data)
                #print json.dumps(prompt)
                #print json.dumps(input_str)
                if input_str.endswith('\r\n' + prompt) or input_str.endswith('\n\r' + prompt):
                    input_str = input_str.replace('\n\r', '\r\n')
                    #print "Got a reply:"
                    tmp = input_str.split(prompt)
                    lines = tmp[-2].split('\r\n')
                    cmd = lines[0]
                    pos = 0
                    for ch in lines[0]:
                        if ch == '\b':
                            pos -= 1
                        else:
                            cmd = cmd[:pos] + ch
                            pos += 1
                    cmd = cmd.strip()
                    lines[0] = cmd
                    if cmd != '':
                        output.append({'cmd': cmd, 'resp': lines[:-1]})
                    #print json.dumps(output, indent=2)
                    input_str = ''
    except serial.SerialException, e:
        print e

if __name__ == "__main__":
    parser = optparse.OptionParser()
    parser.add_option("-d", "--device", dest="device", help="Serial IO device")
    parser.add_option("-p", "--port", dest="port", default='./ttyUSB1', help="Serial port to provide")
    parser.add_option("-o", "--output", dest="output", default='output.json', help="Output json file")
    parser.add_option("-q", "--quiet", action="store_false", dest="verbose", default=True, help="Don't print status messages to stdout")

    (options, args) = parser.parse_args()

    dev_name = '/dev/ttyUSB0'
    if options.device and options.device != '':
        dev_name = options.device
    serial_port = serial.serial_for_url(dev_name, 500000, parity='N', rtscts=False, xonxoff=False, timeout=1)

    provide_port = './ttyUSB1'
    if options.port and options.port != '':
        provide_port = options.port
    args = ['socat', 'pty,link=' + provide_port, 'tcp-l:9009,reuseaddr,fork']
    socat_process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    socat_thread = threading.Thread(target=process_monitor, args=(socat_process, 'socat#: '))
    socat_thread.setDaemon(True)
    socat_thread.start()
    
    time.sleep(1.0)

    # Create a TCP/IP socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_name = '127.0.0.1'
    server_address = (server_name, 9009)
    sock.connect(server_address)
    
    print 'Starting serial reciever thread'
    prompt = u'\u001b[1;32mnanohub-ex\u001b[1;30m # \u001b[0m\u001b[0m'
    output = {'test_prompt': prompt, 'test_cmds': []}
    receiver_thread = threading.Thread(target=serial_reader, args=(prompt, output['test_cmds']))
    receiver_thread.setDaemon(True)
    receiver_thread.start()
        
    try:
#         sock_input = ''
        while True:
            data = sock.recv(16)
            if data and len(data):
                serial_port.write(data)
#                 for ch in data:
#                     print ch
#                     if not ch in string.printable:
#                         print 'Skipping: [' + hex(ord(ch)) + ']'
#                         sock_input = ''
#                     else:
#                         if ch == '\n':
#                             print 'Got a new command: [' + sock_input + ']'
#                         else:
#                             sock_input += ch
    finally:
        print 'closing socket'
        sock.close()
        socat_process.kill()
        socat_thread.join(2)
        if options.output and options.output != '':
            print 'Writing output to ' + options.output
            with open(options.output, 'wt') as fh:
                json.dump(output, fh, indent=2)

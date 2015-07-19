import sys, time, re, os
import subprocess
import serial, threading
import json

if sys.version_info >= (3, 0):
    def character(b):
        return b.decode('latin1')
else:
    def character(b):
        return b

LF = serial.to_bytes([10])
CR = serial.to_bytes([13])
CRLF = serial.to_bytes([13, 10])

CONVERT_CRLF = 2
CONVERT_CR   = 1
CONVERT_LF   = 0
NEWLINE_CONVERSION_MAP = (LF, CR, CRLF)
LF_MODES = ('LF', 'CR', 'CR/LF')

REPR_MODES = ('raw', 'some control', 'all control', 'hex')

class DeviceTester(object):
    def __init__(self, port, baudrate, parity, rtscts=False, xonxoff=False, echo=False, convert_outgoing=CONVERT_CRLF, repr_mode=0):
        try:
            self.serial = serial.serial_for_url(port, baudrate, parity=parity, rtscts=rtscts, xonxoff=xonxoff, timeout=1)
            #self.serial = serial.serial_for_url(port, timeout=1)
        except AttributeError:
            # happens when the installed pyserial is older than 2.5. use the
            # Serial class directly then.
            print "Use serial.Serial"
            self.serial = serial.Serial(port, baudrate, parity=parity, rtscts=rtscts, xonxoff=xonxoff, timeout=1)
        self.echo = echo
        self.repr_mode = repr_mode
        self.convert_outgoing = convert_outgoing
        self.newline = NEWLINE_CONVERSION_MAP[self.convert_outgoing]
        self.dtr_state = True
        self.rts_state = True
        self.break_state = False
        self.curr_data = ''
        self.prompt = '#'
        self.running = False
        self.un_sol_data = ''
        self.report = {'unsolicited':[], 'test_results':[]}
        self.is_ready = threading.Condition()

    def _start_reader(self):
        """Start reader thread"""
        self._reader_alive = True
        # start serial->console thread
        self.receiver_thread = threading.Thread(target=self.reader)
        self.receiver_thread.setDaemon(True)
        self.receiver_thread.start()

    def _stop_reader(self):
        """Stop reader thread only, wait for clean exit of thread"""
        self._reader_alive = False
        self.receiver_thread.join()


    def start(self):
        self.alive = True
        self._start_reader()
        #time.sleep(1.5)

    def stop(self):
        self.alive = False
        self.receiver_thread.join()

    def reader(self):
        """loop and copy serial->console"""
        try:
            while self.alive and self._reader_alive:
                data = self.serial.read(1)
                if data and len(data):
                    if self.running:
                        #print "append to curr: " + data
                        self.is_ready.acquire()
                        self.curr_data += data
                        if self.curr_data.endswith(self.prompt):
                            self.running = False
                            self.is_ready.notify()
                        self.is_ready.release()
                    else:
                        #print "append to un_sol: " + data
                        self.un_sol_data += data
                if (not data or len(self.curr_data)) and len(self.un_sol_data):
                    print 'Unsolicited message: "%s"' % json.dumps(self.un_sol_data).strip('"')
                    self.report['unsolicited'].append({'ts':time.time(), 'msg': self.un_sol_data})
                    self.un_sol_data = ''
                sys.stdout.flush()
        except serial.SerialException, e:
            self.alive = False
            print e
            # would be nice if the console reader could be interruptted at this
            # point...
            raise

    def write(self, data):
        try:
            self.serial.write(data)                    # send byte
        except:
            self.alive = False
            raise

    def sync_target(self, prompt, timeout, delta):
        self.prompt = prompt
        result = False
        while timeout > 0:
            self.curr_data = ''
            self.running = True
            self.write('\n')
            self.is_ready.acquire()
            self.is_ready.wait(delta)
            self.is_ready.release()
            self.running = False
            if self.curr_data == self.prompt:
                print "Ready, got prompt: " + self.curr_data #json.dumps(self.curr_data)
                result = True
                break
            else:
                print "Not prompt: " + json.dumps(self.curr_data)
            timeout -= delta
        return result

    def run_test_cmd(self, test_cmd, expected, prompt=True, timeout=1.5):
#         print "run_test_cmd: [%s] [%s]" % (json.dumps(test_cmd), json.dumps(expected))
#         print "run_test_cmd: [%s] [%s]" % (test_cmd, expected)
        self.curr_data = ''
        self.running = True
        self.write(str(test_cmd))
        self.is_ready.acquire()
        self.is_ready.wait(timeout)
        self.is_ready.release()
        #time.sleep(timeout)
        self.running = False
        result = False
        res_str = 'FAILED'
        compare_str = self.curr_data
        if prompt and compare_str.endswith(self.prompt):
            compare_str = compare_str[0:-len(self.prompt)]
        if compare_str == expected:
            res_str = 'OK'
            result = True
        elif expected != '' and re.match(expected, compare_str):
            res_str = 'OK'
            result = True
        print '%s Exp: [%s] Got: [%s]' % (res_str, json.dumps(expected).strip('"'), json.dumps(compare_str).strip('"'))
        self.report['test_results'].append({'ts':time.time(), 'result':res_str, 'cmd':test_cmd, 'resp':self.curr_data})
        self.curr_data = ''
        return result

    def dump_results(self, filename=None):
        if filename:
            try:
                with open(filename, "wt") as fh:
                    json.dump(self.report, fh, indent=2)
            except:
                print 'Error opening "%s"' % (filename)
        else:
            print json.dumps(self.report, indent=2)
        filename = 'report.rst'
        try:
            with open(filename, 'wt') as fh:
                line_end = '\n'
                fh.write('.. section-numbering::' + 2*line_end)
                fh.write('.. role:: okbox' + 2*line_end)
                fh.write('.. role:: failedbox' + 2*line_end)

                fh.write('Test report' + line_end)
                fh.write('===========' + 2*line_end)
                fh.write('Device under test: ' + 2*line_end)
                fh.write('Unsolicited' + line_end)
                fh.write('***********' + 2*line_end)
                for un_sol in self.report['unsolicited']:
                    output = json.dumps(un_sol['msg']).strip('"').replace('\\', '\\\\').strip()
                    fh.write('msg: : :failedbox:`' + output + '`' + 2*line_end)
                fh.write(2*line_end)
                fh.write('Test commands and results' + line_end)
                fh.write('*************************' + 2*line_end)
                fh.write('List of test commands' + 2*line_end)
                fh.write('----' + 2*line_end)
                for test_result in self.report['test_results']:
                    if test_result['result'] == 'OK':
                        style = 'okbox'
                    else:
                        style = 'failedbox'
                    for record in ['cmd', 'resp', 'result']:
                        output = json.dumps(test_result[record]).strip('"').replace('\\', '\\\\').strip()
                        fh.write(record + ': :' + style + ':`' + output + '`' + 2*line_end)
                    fh.write('----' + 2*line_end)
                fh.write('End of test commands' + 2*line_end)
        except:
            print 'Error opening "%s"' % (filename)


# def dump_port_list():
#     if comports:
#         sys.stderr.write('\n--- Available ports:\n')
#         for port, desc, hwid in sorted(comports()):
#             #~ sys.stderr.write('--- %-20s %s [%s]\n' % (port, desc, hwid))
#             sys.stderr.write('--- %-20s %s\n' % (port, desc))

try:
    from serial.tools.list_ports import comports
except ImportError:
    comports = None

dev_name = 'loop://'
dev_name = 'socket://127.0.0.1:10000'
print "Running serial version " + serial.VERSION + " connecting to " + dev_name

try:
    tester = DeviceTester(dev_name, 500000, 'N')
except serial.SerialException, e:
    sys.stderr.write("could not open port %r: %s\n" % (dev_name, e))
    sys.exit(1)

config = {}
with open('config.json', 'rt') as fh:
    config = json.load(fh)
if not 'test_cmds' in config:
    config['test_cmds'] = []

print "Start tester"
tester.start()

if not tester.sync_target('\033[0;32mnanomind#\033[0m ', 1.5, 0.5):
    print "Failed to initialise test"
else:
    for test_cmd in config['test_cmds']:
        #print json.dumps(test_cmd)
        tester.run_test_cmd(test_cmd['cmd'], test_cmd['resp'])
#     tester.run_test_cmd('\n', '')
#     tester.run_test_cmd('help\n', 'rtc\r\nhelp\r\n')
#     tester.run_test_cmd('cmp ident\n', 'NanoMind\r\n.*\r\n')
#     tester.run_test_cmd('hmc5843 init\n', 'hmc5843 initialised\r\n')
#     tester.run_test_cmd('hmc5843 read\n', 'X: ([0-9\-\.]+) mG\r\nY: ([0-9\-\.]+) mG\r\nZ: ([0-9\-\.]+) mG\r\nMagnitude: ([0-9\-\.]+) mG')
#     tester.run_test_cmd('hmc5843 loop\n', 'hmc5843 initialised\r\n')

print "Stop tester"

tester.stop()

print 'Generating test report'
tester.dump_results('report.json')

print 'Generating pdf report'
if os.path.exists('report.pdf'):
    os.remove('report.pdf')
args = ['rst2pdf', 'report.rst', '-s', 'report.style', '-o', 'report.pdf']
p = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
for line in p.stdout.readlines():
    print '##: ' + line

print "Done"
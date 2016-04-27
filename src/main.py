import os
import sys
import time
import re
import subprocess
import threading
import json
import optparse
import serial

class DeviceTester(object):
    def __init__(self, port, baudrate, parity):
        try:
            self.serial = serial.serial_for_url(port, baudrate, parity=parity, rtscts=False, xonxoff=False, timeout=1)
        except AttributeError:
            # happens when the installed pyserial is older than 2.5. use the
            print "You must install serial version >= 2.5"
            raise
        self.curr_data = ''
        self.prompt = '#'
        self.running = False
        self.un_sol_data = ''
        self.report = {'unsolicited':[], 'test_results':[]}
        self.is_ready = threading.Condition()
        self.device_uid = 'DEADBEEFDEADBEEF'

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
            for ch in data.encode('utf-8'):
                self.serial.write(ch)                    # send byte
                time.sleep(0.01)
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
            #if self.curr_data == self.prompt:
            if self.curr_data.endswith(self.prompt):
                print "Ready, got prompt: " + self.curr_data #json.dumps(self.curr_data)
                result = True
                break
            else:
                print "Not prompt: "
                print json.dumps(self.curr_data)
                print json.dumps('\r\n' + self.prompt)
            timeout -= delta
        return result

    def run_test_cmd(self, test_cmd, expected, reg_ex, prompt=True, timeout=1.5):
#         print "run_test_cmd: [%s] [%s]" % (json.dumps(test_cmd), json.dumps(expected))
#         print "run_test_cmd: [%s] [%s]" % (test_cmd, expected)
        if type(expected) is list:
            expected = '\r\n'.join(expected) + '\r\n'
        self.curr_data = ''
        self.running = True
        self.write(test_cmd.rstrip() + '\n')
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
        compare_str = compare_str.replace('\n\r', '\r\n')
        expected = expected.replace('\r', '')
        compare_str = compare_str.replace('\r', '')
        if compare_str == expected:
            res_str = 'OK'
            result = True
        elif reg_ex:
            #print "Check re '{0}' '{1}'".format(expected, compare_str)
            if re.match(expected, compare_str):
                res_str = 'OK (regex)'
                result = True
        else:
#             expected = expected.replace('%', '\%')
#             expected = expected.replace('|', '\|')
#             expected = expected.replace('[', '\[')
#             expected = expected.replace(']', '\]')
#             expected = expected.replace('{', '\{')
#             expected = expected.replace('}', '\}')
#             expected = expected.replace('(', '\(')
#             expected = expected.replace(')', '\)')
            tmp_e = expected.split('\n')
            tmp_c = compare_str.split('\n')
            result = True
            res_str = 'OK (re)'
            for (exp_line, cmp_line) in zip(tmp_e, tmp_c):
                if exp_line == cmp_line:
                    continue
                for repl in '(){}[]|%-+<>':
                    exp_line = exp_line.replace(repl, '\\' + repl)
                expr = re.compile('([:|=\( ]\s*)([+|-]*[0-9.]+)')
                (exp_line, cnt) = expr.subn('\g<1>([+|-]*[0-9.]+)', exp_line)
                exp_line = '\s*' + '\s*'.join(exp_line.split()) + '\s*'
                #print "cnt: {0} compare\n'{1}'\n'{2}'".format(cnt, exp_line, cmp_line)
                if cnt > 0 and re.compile(exp_line).match(cmp_line):
                    pass
                else:
                    result = False
                    res_str = 'FAILED'
                    break
        if False:
            #expr = re.compile('([:|=\(]\s*)([0-9-.]+)')
            expr = re.compile('([:|=\( ]\s*)([0-9-.]+)')
            (expected, cnt) = expr.subn('\g<1>([0-9-.]+)', expected)
            if cnt > 0 and re.match(expected, compare_str):
                res_str = 'OK (re)'
                result = True
#         elif expected != '' and re.match(expected, compare_str):
#             res_str = 'OK (re)'
#             result = True
        #print '%s Exp: [%s] Got: [%s]' % (res_str, json.dumps(expected).strip('"'), json.dumps(compare_str).strip('"'))
        if re.match('OK', res_str):
            sys.stdout.write('\033[0;32m')
        else:
            sys.stdout.write('\033[0;31m')
        print 'cmd: ' + test_cmd  + ' - ' + res_str
        sys.stdout.write('\033[0m')
        self.report['test_results'].append({'ts':time.time(), 'result':res_str, 'cmd':test_cmd, 'resp':compare_str, 'expected': expected})
        self.curr_data = ''
        return result

    def dump_results(self, rst_filename, json_filename=None):
        if json_filename:
            try:
                with open(json_filename, "wt") as fh:
                    json.dump(self.report, fh, indent=2)
            except:
                print 'Error opening "%s"' % (json_filename)
        else:
            print json.dumps(self.report, indent=2)
        try:
            with open(rst_filename, 'wt') as fh:
                line_end = '\n'
                fh.write('.. section-numbering::' + 2*line_end)
                fh.write('.. role:: okbox' + 2*line_end)
                fh.write('.. role:: failedbox' + 2*line_end)

                fh.write('Test report' + line_end)
                fh.write('===========' + 2*line_end)
                fh.write('Device under test: ' + self.device_uid + 2*line_end)
                output = json.dumps(self.prompt).strip('"').replace('\\', '\\\\').strip()
                fh.write('Prompt: ' + output + '' + 2*line_end)
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
                ok_cnt = 0
                failed_cnt = 0
                total_cnt = 0
                fh.write('.. csv-table:: Test commands and results' + line_end)
                fh.write('   :header: "Command", "Result"' + line_end)
                fh.write('   :widths: 40, 10' + 2*line_end)
                for test_result in self.report['test_results']:
                    total_cnt += 1
                    if re.match('OK', test_result['result']) != None:
                        style = 'okbox'
                        ok_cnt += 1
                    else:
                        style = 'failedbox'
                        failed_cnt += 1
                    fh.write('   "' + test_result['cmd'] + '", "\'\\ :' + style + ':`' + test_result['result'] + '`\\ \'"' + line_end)
                fh.write(line_end)

                fh.write('.. csv-table:: Summary of test commands' + line_end)
                #fh.write('   :header: "Command", "Result"' + line_end)
                fh.write('   :widths: 20, 10' + 2*line_end)
                fh.write('   "Total test commands", "' + str(total_cnt) + '"' + line_end)
                fh.write('   "OK test commands", "' + str(ok_cnt) + '"' + line_end)
                fh.write('   "Failed test commands", "' + str(failed_cnt) + '"' + line_end)

                fh.write(2*line_end)
                fh.write('Test commands and results detailed' + line_end)
                fh.write('**********************************' + 2*line_end)
                fh.write('List of test commands' + 2*line_end)
                fh.write('----' + 2*line_end)
                for test_result in self.report['test_results']:
                    if re.match('OK', test_result['result']) != None:
                        style = 'okbox'
                    else:
                        style = 'failedbox'
                    for record in ['cmd', 'result']:
                        output = json.dumps(test_result[record]).strip('"').replace('\\', '\\\\').strip()
                        if output == '':
                            fh.write(record + ': ' + 2*line_end)
                        else:
                            fh.write(record + ': :' + style + ':`' + output + '`' + 2*line_end)
                    for record in ['resp', 'expected']:
                        fh.write(record.title() + '::' +2*line_end)
                        lines = test_result[record].split('\n')
                        for line in lines:
                            fh.write('   ' + line + line_end)
                        fh.write(line_end)
                        
                    fh.write('----' + 2*line_end)
                fh.write('End of test report' + 2*line_end)
        except:
            print 'Error opening "%s"' % (rst_filename)


if __name__ == "__main__":
    parser = optparse.OptionParser()
    parser.add_option("-d", "--device", dest="device", help="Serial IO device")
    parser.add_option("-c", "--config", dest="config", default='config.json', help="Config file")
    parser.add_option("-r", "--report", dest="report", default='report', help="Report file")
    parser.add_option("-q", "--quiet", action="store_false", dest="verbose", default=True, help="Don't print status messages to stdout")

    (options, args) = parser.parse_args()

    dev_name = 'loop://'
    dev_name = 'socket://127.0.0.1:10000'
    if options.device and options.device != '':
        dev_name = options.device

    print "Running serial version " + serial.VERSION + " connecting to " + dev_name
    
    try:
        tester = DeviceTester(dev_name, 500000, 'N')
    except serial.SerialException, e:
        sys.stderr.write("Could not open device %r: %s\n" % (dev_name, e))
        sys.exit(1)
    
    config_file = options.config
    print 'Loading config from: ' + config_file
    config = {}
    with open(config_file, 'rt') as fh:
        config = json.load(fh)
    if not 'test_cmds' in config:
        config['test_cmds'] = []
    if not 'test_prompt' in config:
        config['test_prompt'] = ''
    test_prompt = unicode(config['test_prompt'])

#     print 'test_prompt: ' + test_prompt
    
    print "Start tester"
    tester.start()
    
    if not tester.sync_target(test_prompt, 1.5, 0.5):
        print "Failed to initialise test"
    else:
        for test_cmd in config['test_cmds']:
            reg_ex = True if ('regex' in test_cmd and test_cmd['regex'] == True) else False
            tester.run_test_cmd(test_cmd['cmd'], test_cmd['resp'], reg_ex)
            time.sleep(0.1)
    
    print "Stop tester"
    
    tester.stop()
    
    json_report = 'report.json'
    rst_report = 'report.rst'
    print 'Generating test report: ' + json_report
    tester.dump_results(rst_report, json_report)
    
    pdf_report = options.report + '.pdf'
    print 'Generating pdf report: ' + pdf_report
    if os.path.exists(pdf_report):
        os.remove(pdf_report)
    args = ['rst2pdf', rst_report, '-s', 'report.style', '-o', pdf_report]
    p = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    for line in p.stdout.readlines():
        print '##: ' + line
    
    print "Done"
    
#[+-]?((\d+(\.\d*)?)

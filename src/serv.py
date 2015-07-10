import socket
import sys
import time
import cmd

# Create a TCP/IP socket
sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

# Bind the socket to the address given on the command line
server_name = '127.0.0.1'
server_address = (server_name, 10000)
print >>sys.stderr, 'starting up on %s port %s' % server_address
sock.bind(server_address)
sock.listen(1)

while True:
    print >>sys.stderr, 'waiting for a connection'
    connection, client_address = sock.accept()
    try:
        print 'client connected:', client_address
        reply = '\033[0;31mError message\033[0m\r\n'
        print '>>> send "%s"' % reply.replace('\r\n', '\\r\\n')
        connection.sendall(reply)
        while True:
            data = connection.recv(256)
            print '<<< recv "%s"' % data.replace("\n", "\\n")
            reply = ''
            if data and data[-1] == '\n':
                cmd = data.strip()
                if cmd == 'help':
                    reply += 'rtc\r\n'
                    reply += 'help\r\n'
                elif cmd == 'cmp ident':
                    reply += 'NanoMind\r\nv0.3\r\n'
                elif cmd == 'hmc5843 init':
                    reply += 'hmc5843 initialised\r\n'
                elif cmd == 'hmc5843 read':
                    reply += 'X: -123 mG\r\nY: -456 mG\r\nZ: -789 mG\r\nMagnitude: -123 mG\r\n'
                elif cmd != '':
                    reply += 'Unknown command \'%s\'\r\n' % cmd
                print '>>> send "%s"' % reply.replace('\r\n', '\\r\\n')
                connection.sendall(reply)
                time.sleep(0.3)
                reply = '\033[0;32mnanomind#\033[0m '
                print '>>> send "%s"' % reply.replace('\r\n', '\\r\\n')
                connection.sendall(reply)
            else:
                break
    finally:
        connection.close()

#"Could not execute command \'%s\', Invalid argument(s)\r\n", org);
#"Could not execute command \'%s\', error %d\r\n", org, ret)

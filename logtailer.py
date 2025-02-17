#!/usr/bin/python3 
# -*- coding: utf-8 -*-

import datetime
import os.path
import asyncio
import logging
import argparse
import websockets
import socketserver
import configparser
import os
from collections import deque
from urllib.parse import urlparse, parse_qs
from ansi2html import Ansi2HTMLConverter
from os import popen
import psutil
import ssl
import subprocess
import time

current_dir = os.getcwd()
config = configparser.ConfigParser()
config.read(current_dir + '/logtailer.ini')

dmrids = {}

# init
logging.basicConfig(format='%(asctime)s %(levelname)s %(message)s', level=logging.INFO)
conv = Ansi2HTMLConverter(inline=True)

async def view_log(websocket, path=None):
    global config
    global dmrids

    # path argument of connection handlers is "unnecessary since 10.1 and deprecated in 13.0
    if path is None:
        path = websocket.request.path
    logging.info('Connected, remote={}, path={}'.format(websocket.remote_address, path))

    try:
        try:
            parse_result = urlparse(path)
        except Exception:
            raise ValueError('Fail to parse URL', format(path))

        path = os.path.abspath(parse_result.path)
        now = datetime.datetime.now(datetime.timezone.utc)
        year = str(now.year)
        month = str(now.month)
        if len(month) == 1:
            month = "0" + month
        day = str(now.day)
        if len(day) == 1:
            day = "0" + day
        
        file_path = ""
        if path.startswith("/YSFReflector"):
            if config['DEFAULT']['Filerotate'] == "True":
                file_path = config[path[1:]]['Logdir']+config[path[1:]]['Prefix']+"-"+year+"-"+month+"-"+day+".log"
            else:
                file_path = config[path[1:]]['Logdir']+config[path[1:]]['Prefix']+".log"
            logging.info(file_path)
            
            if not os.path.isfile(file_path):
                raise ValueError('File not found', format(file_path))

            with open(file_path, newline = '\n', encoding="utf8", errors='ignore') as f:
                content = ''.join(deque(f, int(config['DEFAULT']['MaxLines'])))
                content = conv.convert(content, full=False)
                lines = content.split("\n")
                for line in lines:
                    if line.find("received") > 0 or line.find("network watchdog") > 0:
                        if line.find("from ") > 0 and line.find("to ") > 0:
                            source = line[line.index("from ") + 5:line.index("to ")].strip()
                            if source in dmrids:
                                line = line.replace(source, dmrids[source])
                        if line.find("to ") > 0:
                            if line.find("at ") > 0 and line.find("late entry") < 0:
                                target = line[line.index("to ") + 3:line.rindex("at ")]
                                if target in dmrids:
                                    line = line.replace(target, dmrids[target])
                            else:
                                target = line[line.index("to") + 3:]
                                if target.find(",") > 0:
                                    target = target[0:target.index(",")]
                                if target in dmrids:
                                    line = line.replace(target, dmrids[target])
                    await websocket.send(line)

                while True:
                    content = f.read()
                    if content:
                        content = conv.convert(content, full=False)
                        lines = content.split("\n")
                        for line in lines:
                            if line.find("received") > 0 or line.find("network watchdog") > 0:
                                if line.find("from ") > 0 and line.find("to ") > 0:
                                    source = line[line.index("from ") + 5:line.index("to ")].strip()
                                    if source in dmrids:
                                        line = line.replace(source, dmrids[source])
                                if line.find("to ") > 0:
                                    if line.find("at ") > 0 and line.find("late entry") < 0:
                                        target = line[line.index("to ") + 3:line.rindex("at ")]
                                        if target in dmrids:
                                            line = line.replace(target, dmrids[target])
                                    else:
                                        target = line[line.index("to") + 3:]
                                        if target.find(",") > 0:
                                            target = target[0:target.index(",")]
                                        if target in dmrids:
                                            line = line.replace(target, dmrids[target])
                            await websocket.send(line)
                    else:
                        await asyncio.sleep(0.2)
        elif path == "/SYSINFO":
            ysfreflector_version = str(subprocess.Popen(config['YSFReflector']['YSFReflector_bin'] + " -v", shell=True, stdout=subprocess.PIPE).stdout.read().decode("utf-8"))
            ysfreflector_ctime = time.ctime(os.path.getmtime(config['YSFReflector']['YSFReflector_bin']))
            ysfreflector_buildtime = datetime.datetime.strptime(ysfreflector_ctime, "%a %b %d %H:%M:%S %Y")
            await websocket.send("REFLECTORINFO: ysfreflector_version:" + ysfreflector_version + " ysfreflector_ctime:" + ysfreflector_ctime)
            await asyncio.sleep(1)
            while True:
                cpu_temp = ""
                temps = psutil.sensors_temperatures()
                if not temps:
                    cpu_temp = "N/A"
                for name, entries in temps.items():
                    for entry in entries:
                        cpu_temp = str(entry.current)
                cpufrqs = psutil.cpu_freq()
                cpufrq = "N/A"
                if cpufrqs:
                    cpufrq = str(cpufrqs.current)
                cpu_usage = str(psutil.cpu_percent())
                cpu_load = os.getloadavg();
                cpu_load1 = str(cpu_load[0])
                cpu_load5 = str(cpu_load[1])
                cpu_load15 = str(cpu_load[2])
                
                ram = psutil.virtual_memory()
                ram_total = str(ram.total / 2**20)
                ram_used = str(ram.used / 2**20)
                ram_free = str(ram.free / 2**20)
                ram_percent_used = str(ram.percent)
                
                disk = psutil.disk_usage('/')
                disk_total = str(disk.total / 2**30)
                disk_used = str(disk.used / 2**30)
                disk_free = str(disk.free / 2**30)
                disk_percent_used = str(disk.percent)
                await websocket.send("SYSINFO: cputemp:" + cpu_temp + " cpufrg:" + cpufrq + " cpuusage:" + cpu_usage + " cpu_load1:" + cpu_load1 + " cpu_load5:" + cpu_load5 + " cpu_load15:" + cpu_load15 + " ram_total:" + ram_total + " ram_used:" + ram_used + " ram_free:" + ram_free + " ram_percent_used:" + ram_percent_used + " disk_total:" + disk_total + " disk_used:" + disk_used + " disk_free:" + disk_free + " disk_percent_used:" + disk_percent_used)
                await asyncio.sleep(10)

    except ValueError as e:
        try:
            await websocket.send('Logtailer-Errormessage: ValueError: {}'.format(e))
            await websocket.close()
        except Exception:
            pass

        log_close(websocket, path, e)

    except Exception as e:
        try:
            await websocket.send('Logtailer-Errormessage: Error: {}'.format(e))
            await websocket.close()
        except Exception:
            pass
        log_close(websocket, path, e)

    else:
        log_close(websocket, path)


def log_close(websocket, path, exception=None):
    message = 'Closed, remote={}, path={}'.format(websocket.remote_address, path)
    if exception is not None:
        message += ', exception={}'.format(exception)
    logging.info(message)


async def websocketserver():
    start_server = None
    if (config['DEFAULT']['Ssl'] == "True"):
        ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        cert_pem = config['DEFAULT']['SslCert']
        key_pem = config['DEFAULT']['SslKey']

        ssl_context.load_cert_chain(cert_pem, key_pem)
        start_server = await websockets.serve(view_log, config['DEFAULT']['Host'], config['DEFAULT']['Port'], ssl=ssl_context)
    else:
        start_server = await websockets.serve(view_log, config['DEFAULT']['Host'], config['DEFAULT']['Port'])

    await start_server.wait_closed()

def main():
    logging.info("Starting Websocketserver")
    asyncio.run(websocketserver())


if __name__ == '__main__':
    main()

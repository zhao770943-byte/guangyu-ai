"""User-session supervision. Never kills processes or reposts generation jobs."""
import ctypes
from ctypes import wintypes
import logging
import json
from datetime import datetime,timezone
from logging.handlers import RotatingFileHandler
import os
import sys
import time
import launcher

INTERVAL=10

def singleton(name):
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.CreateMutexW.argtypes=[ctypes.c_void_p,wintypes.BOOL,wintypes.LPCWSTR]
    kernel.CreateMutexW.restype=wintypes.HANDLE
    kernel.CloseHandle.argtypes=[wintypes.HANDLE]
    handle=kernel.CreateMutexW(None,False,name)
    if not handle:raise OSError(ctypes.get_last_error(),'Cannot create supervisor mutex')
    if ctypes.get_last_error()==183:
        kernel.CloseHandle(handle);return None
    return handle

def keep_awake(enabled):
    class Power(ctypes.Structure):
        _fields_=[('ac',ctypes.c_ubyte),('battery',ctypes.c_ubyte),('percent',ctypes.c_ubyte),
                  ('reserved',ctypes.c_ubyte),('life',wintypes.DWORD),('full',wintypes.DWORD)]
    power=Power();kernel=ctypes.windll.kernel32
    on_ac=bool(kernel.GetSystemPowerStatus(ctypes.byref(power))) and power.ac==1
    # Keep the system awake on AC only; do not keep the display on or change power plans.
    kernel.SetThreadExecutionState.argtypes=[wintypes.DWORD]
    kernel.SetThreadExecutionState.restype=wintypes.DWORD
    accepted=kernel.SetThreadExecutionState(0x80000000 | (1 if enabled and on_ac else 0))
    return bool(accepted) and enabled and on_ac

def ensure_service(opener,origin,data):
    if (data/'service.paused').exists():return 'paused'
    try:
        health=launcher.read(opener,origin,'/api/health')
    except (OSError,ValueError):health=None
    if isinstance(health,dict) and health.get('app')=='GuangyuAI' and health.get('instance')==launcher.instance_id(data):
        return 'healthy'
    # Existing launcher validates port/instance identity and never terminates another service.
    launcher.main(['--no-browser','--supervised'])
    return 'recovered'

def main(args=None):
    args=list(sys.argv[1:] if args is None else args)
    if set(args)-{'--keep-awake-ac','--no-browser'}:raise ValueError('Unsupported supervisor arguments')
    if os.name!='nt':raise RuntimeError('Windows supervisor only')
    port,origin,data=launcher.configuration();data.mkdir(parents=True,exist_ok=True)
    handle=singleton('Local\\GuangyuAI-Watchdog-'+launcher.instance_id(data)+'-'+str(port))
    if handle is None:return 0
    logger=logging.getLogger('guangyu.watchdog');logger.setLevel(logging.INFO)
    log=RotatingFileHandler(data/'watchdog.log',maxBytes=1024*1024,backupCount=2,encoding='utf-8')
    log.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'));logger.addHandler(log)
    logger.info('Supervisor started pid=%s port=%s',os.getpid(),port)
    previous=None;opener=launcher.local_opener()
    try:
        while True:
            try:state=ensure_service(opener,origin,data)
            except Exception as ex:state='unavailable: '+str(ex)[:400]
            if state!=previous:logger.info('%s',state);previous=state
            awake=keep_awake('--keep-awake-ac' in args and state in ('healthy','recovered'))
            status={'pid':os.getpid(),'state':state,'keep_awake_ac':awake,'updated_at':datetime.now(timezone.utc).isoformat()}
            temp=data/'watchdog-status.tmp'
            temp.write_text(json.dumps(status),encoding='utf-8');temp.replace(data/'watchdog-status.json')
            time.sleep(INTERVAL)
    finally:
        keep_awake(False)
        kernel=ctypes.WinDLL('kernel32');kernel.CloseHandle.argtypes=[wintypes.HANDLE];kernel.CloseHandle(handle)

if __name__=='__main__':sys.exit(main())

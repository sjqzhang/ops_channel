#!/usr/bin/env python
# -*- coding:utf8 -*-
__author__ = 'xiaozhang'

import sys
import os
PY2 = sys.version_info[0] == 2
PY3 = sys.version_info[0] == 3
import requests
# if PY2:
#     import urllib2 as urllib2
#     from urlparse import urlparse
# if PY3:
#     import urllib.request as urllib2
#     import urllib.parse as urlparse
# import urllib
from codeigniter import ci
from codeigniter import cache
from codeigniter import CI_Cache
import os
import json
import re
import sys
import time
import base64
import datetime
import socket
import Queue
import random
# from sql4json.sql4json import *
from functools import wraps

try:
    import gevent
except:
    pass





import threading



# import cProfile
# import pstats
# import os
# def do_cprofile(filename):
#     """
#     Decorator for function profiling.
#     """
#     def wrapper(func):
#         def profiled_func(*args, **kwargs):
#             # Flag for do profiling or not.
#             DO_PROF = os.getenv("PROFILING")
#             DO_PROF =True
#             if DO_PROF:
#                 profile = cProfile.Profile()
#                 profile.enable()
#                 result = func(*args, **kwargs)
#                 profile.disable()
#                 # Sort stat by internal time.
#                 sortby = "tottime"
#                 ps = pstats.Stats(profile).sort_stats(sortby)
#                 ps.dump_stats(filename)
#             else:
#                 result = func(*args, **kwargs)
#             return result
#         return profiled_func
#     return wrapper

def auth(func):
    def decorated(*arg,**kwargs):
        if not 'HTTP_AUTH_UUID' in ci.local.env:
            return "(error)unauthorize1"
        if ci.redis.get('login_'+ci.local.env['HTTP_AUTH_UUID'])==None:
            return "(error)unauthorize"
        return func(*arg,**kwargs)
    return decorated

FP_LOG=open('exec_time','a')

def exec_time(func):
    @wraps(func)
    def decorated(*arg,**kwargs):
        s=time.time()
        ret= func(*arg,**kwargs)
        e=time.time()
        msg='%s:%s'%(str(func),str(e-s))
        FP_LOG.write(msg)
        return ret
    return decorated

def error_notify(func):
    def decorated(*arg,**kwargs):
        try:
            return func(*arg,**kwargs)
        except Exception as er:
            ci.redis.lpush( 'errors', json.dumps({'message':str(er),'function':str(func),'time':time.strftime( '%Y-%m-%d %H:%M:%S')}))
            ci.redis.ltrim('errors',0,500)
            raise Exception(er)
    return decorated


class HeartBeat(object):

    _singleton=False



    def __init__(self):
        self.filename='heartbeat.json'
        self.UUIDS_KEY='uuids'
        self.data=[]# {'uuid','status','utime','salt','ips','hostname','system_os','ip'}
        self.load_data()
        self.uuids=set()


    def ip2uuid(self,data):
        if 'ips' in data.keys():
            p=ci.redis.pipeline()
            for ip in data['ips'].split(','):
                if ip!='127.0.0.1':
                    p.sadd(ip,data['uuid'])
            p.execute()



    def check_online(self):
        while True:
            try:
                self.check_status()
                time.sleep(60*2)
            except Exception as er:
                pass


    def confirm_offline(self,uuid=''):
        self.check_status()
        offline=[]
        result=[]
        for d in self.data:
            if d['status']=='online':
                result.append(d)
            elif d['status']=='offline':
                offline.append(d['uuid'])
        self.data=result
        self.dump_data()
        p=ci.redis.pipeline()
        if uuid!='':
            if uuid in offline:
                ci.redis.srem(self.UUIDS_KEY,uuid)
                return 'ok'
            else:
                return '(error) %s is not in offline status' %(uuid)
        for off in offline:
            p.srem(self.UUIDS_KEY,off)
        p.execute()
        return 'ok'


    def check_status(self):
        uuids=ci.redis.smembers("uuids")
        p=ci.redis.pipeline()
        for i in uuids:
            p.get(i)
        data=[]
        for i in p.execute():
            try:
                if i==None:
                    continue
                d=json.loads(i)
                data.append(d)
            except Exception as er:
                ci.logger.error(i)
                pass
        self.data = data
        #self.data= map(lambda x:json.loads(x),p.execute())

        now=int(time.time())
        for d in self.data:
            if now-d['utime']>60*10:
                ci.redis.srem('uuids',d['uuid'])
                ci.redis.delete(d['uuid'])
                d['status']='offline'
            else:
                d['status'] = 'online'





    def status(self):

        self.check_status()
        result={'offline':0,'online':0,'count':0}
        for d in self.data:
            result['count']= result['count']+1
            if d['status']=='offline':
                result['offline']=result['offline']+1
            elif  d['status']=='online':
                result['online']=result['online']+1
        return  result

    def listclient(self):
        self.check_status()
        result=[]
        fields=['status','uuid','utime','ip','hostname']
        for row in self.data:
            d={}
            for i in fields:
                d[i]=row[i]
            d['utime']=  time.strftime( '%Y-%m-%d %H:%M:%S',time.localtime(d['utime']))
            result.append(d)
        return  result


    def _status_line(self,status='offline'):
        self.check_status()
        result=[]
        for d in self.data:
            if d['status']==status:
                d['utime']=  time.strftime( '%Y-%m-%d %H:%M:%S',time.localtime(d['utime']))
                for i in ['ips','salt','status_os']:
                    if i in d:
                        del d[i]
                result.append(d)
        return  result


    def offline(self):
        return self._status_line(status='offline')


    def online(self):
        return self._status_line(status='online')

    def getetcd(self,param):
        etcd=ci.config.get('etcd',{'server':['127.0.0.1'],'prefix':'/keeper'})
        if 'app' in etcd:
            del etcd['app']
        return etcd


    # @cache.Cache()
    def heartbeat(self,params):
        status=''
        hostname=''
        ip=''
        platform=''
        if 'status'  in params.keys():
            status=params['status'].strip()

        if 'uuid' not in params.keys() and  len(params['uuid'])!=36:
            self.remove(params['uuid'])
            return '(error) invalid request'
        if 'hostname' in params.keys():
            hostname=params['hostname']
        if 'ip' in params.keys():
            ip=params['ip']
        if 'platform' in params.keys():
            platform=params['platform']
        objs=self.get_product_uuid(params['uuid'])
        # self.uuids.add(params['uuid'])
        ci.redis.sadd(self.UUIDS_KEY,params['uuid'])

        salt= str(ci.uuid())
        utime=int(time.time())

        if objs==None or len(objs)==0:
            param={'uuid':params['uuid'],'salt':salt,'ips':params['ips'],'utime':utime,'status':'online','status_os':status,'hostname':hostname,'ip':ip,'platform':platform}
            # self.data.append(param)
            ci.redis.set(params['uuid'],json.dumps(param))
            # self.ip2uuid( param)
        elif len(objs)==1:
            if 'salt' in objs[0].keys():
                salt=objs[0]['salt']
            param={'uuid':params['uuid'],'salt':salt,'ips':params['ips'],'utime':utime,'status':'online','status_os':status,'hostname':hostname,'ip':ip,'platform':platform}
            # self.ip2uuid(param)
            ci.redis.set(params['uuid'], json.dumps( param))
        else:
            ci.logger.error('heartbeat double: uuid=%s,ips=%s'%(params['uuid'],params['ips']))


        etcd=self.getetcd(params)

        if status!='' and status!='{}':
            return {'etcd':etcd, 'salt':salt}
        else:
            return {'etcd':etcd, 'salt':salt,'shell':self.shellstr()}



    def get_product_uuid(self,ip):
        ret=[]
        if len(ip)>16:# use uuid search
            objs=ci.redis.get(ip)
            if objs!=None:
                ret.append(json.loads(objs))

        if len(ret)>0 or len(ip)>16:
            return ret
        else:
            self.check_status()
            objs=ci.loader.helper('DictUtil').query(self.data,select='*',where="((ips in %s) or (uuid=%s))"% (ip,ip))
            return objs

    def load_data(self):
        if os.path.isfile(self.filename):
            with open(self.filename,'r') as file:
                self.data=json.loads( file.read())

    def dump_data(self):
        with open(self.filename,'w+') as file:
            file.write(json.dumps(self.data))

    def shellstr(self):
        shell='''
#!/bin/sh
disk=`df | awk 'BEGIN{total=0;avl=0;used=0;}NR > 1{total+=$2;used+=$3;avl+=$4;}END{printf"%d", used/total*100}'`
#mem=`top -b -d 1 -n 2 | grep -w Mem | awk 'END{printf"%d",$4/$2*100}'`
mem=`free |grep -w "Mem:" |awk '{printf"%d", $3/$2*100}'`
cpu=`top -b -n 2 -d 1 | grep -w Cpu |awk -F ',|  ' 'END{print $2+$3}'`
net=`ss -s |grep -w 'Total:'|awk '{print $2}'`
iowait=`top -n 2 -b -d 1  |grep -w 'Cpu' |awk '{print $6}'|awk -F '%' 'END {print $1}'`
load=`top -n 2 -d 1  -b |grep -w average: |awk -F',' 'END{printf"%3.2f",$5}'`
echo '{"cpu":'$cpu,'"disk":'$disk,'"mem":'$mem,'"net":'$net,'"iowait":'$iowait,'"load":'$load }
        '''
        file_name='stats.py'
        if os.path.exists(file_name):
            return open(file_name,'r').read()
        return shell


class Cli:

    GLOBAL_IP2UUID={}
    GLOBAL_UUID2IP={}
    GLOBAL_UUID2SALT={}
    GLOBAL_UUIDS=set()
    GLOBAL_UUID2UTIME={}

    def __init__(self):
        self.cmdkeys={}
        self.HEARTBEAT_LIST_KEY='heartbeats'
        self.RESULT_LIST_KEY='results'
        self.AUTH_KEY_PREFIX='auth_'
        self.TOKEN_LIST_KEY='tokens'
        self.UUIDS_KEY='uuids'
        self.SYSTEM_STATUS_LIST_KEY='system_status'
        self.TASK_LIST_KEY='indexs'
        self.CMDB_OPTION_PREFIX='cmdb_options_'
        self.HEARTBEAT_UUID_MAP_IP_KEY='heartbeat_uuid_ip'
        self.HEARTBEAT_IP_MAP_UUID_KEY='heartbeat_ip_uuid'
        self.GOOGLE_AUTH_KEY_PREFIX='google_auth_%s_%s'
        self.COMMNAD_PREFIX='cmd_'
        self.GET_OBJS_KEY_PREFIX='get_objs_'
        self.GET_OBJS_KEY_GROUP = 'get_objs_group'
        self.CACHE_KEY_PREFIX='outer_'
        self.VM_TASK_KEY_GROUP='vm'
        self.RESULT_KEY_PREFIX='result_'
        self.CHANNEL_TABLE_PREFIX='t_ch_'
        self.FILE_CACHE_KEY_PREFIX='files_'
        self.CHANNEL_FIELD_PREFIX='F'
        self.ETCD_USER='root'
        self.ETCD_PASSOWRD='root'
        self.UPLOAD_DIR='files'
        self.OTYPE_CHECK_NAME='otype_check'
        self.OBJS_LIST_KEY='objs'
        self.ERROR_KEY='errors'
        self.MYSQL_VERSION=''
        self.HEADER_MACHINE_ID='HTTP_MACHINE_ID'
        self._cmdb=None
        self.hb=HeartBeat()
        self.has_hd2db=False
        self.has_result2db=False
        self.has_hb2influxdb=False
        self.has_buildindex=False
        self.has_refresh_machine=False
        self.opener=requests.session()
        self.init()


    def init(self):
        cert=ci.config.get('certificate',{})
        key_file=cert.get('key_file','/etc/cli/etcd-worker-key.pem')
        cert_file=cert.get('cert_file','/etc/cli/etcd-worker.pem')
        self.opener.cert=( cert_file,key_file )
        if not os.path.isdir(self.UPLOAD_DIR):
            os.mkdir(self.UPLOAD_DIR)
        self.ETCD_USER= ci.config.get('etcd_root',{}).get('user','root')
        self.ETCD_PASSOWRD = ci.config.get('etcd_root', {}).get('password', 'root')
        self.ETCD_BASIC_AUTH = 'Basic ' + base64.encodestring(self.ETCD_USER + ':' + self.ETCD_PASSOWRD).strip()
        th_refresh_uptime=threading.Thread(target=self._refresh_utime)
        th_refresh_uptime.setDaemon(True)
        #th_refresh_uptime.start()

    def trim_double_uuid(self,req,resp):
        d = {}
        double_uuid = []
        ret={}
        uuids = self.GLOBAL_IP2UUID.values()
        for uuid in uuids:
            d[uuid] = uuids.count(uuid)
        for k, v in d.iteritems():
            if v > 1:
                double_uuid.append(k)
                ci.redis.hdel(self.HEARTBEAT_UUID_MAP_IP_KEY, k)
        for k, v in self.GLOBAL_IP2UUID.iteritems():
            if v in double_uuid:
                ret[k]=v
                ci.redis.hdel(self.HEARTBEAT_IP_MAP_UUID_KEY, k)
        for u in double_uuid:
            ci.redis.srem(self.UUIDS_KEY, u)
        return ret

    def _refresh_utime(self):
        while True:
            try:
                self.hb.check_status()
                for d in self.hb.data:
                    self.GLOBAL_UUID2SALT[d['uuid']] = d['salt']
                    self.GLOBAL_UUID2UTIME[d['uuid']] = d['utime']

                time.sleep(60)
            except Exception as er:
                print(er)
                ci.logger.error(er)



    def _load_uuid_info(self):
        def load_data():
            while True:
                try:
                    self.hb.check_status()
                    for hb in self.hb.data:
                        if hb['status']=='online' or hb['utime']:
                            if 'uuid' in hb and len(hb)>3:
                                self.GLOBAL_IP2UUID[hb['ip']]=hb['uuid']
                                self.GLOBAL_UUID2IP[hb['uuid']]=hb['ip']
                                self.GLOBAL_UUIDS.add(hb['uuid'])
                                self.GLOBAL_UUID2SALT[hb['uuid']] = hb['salt']
                                self.GLOBAL_UUID2UTIME[hb['uuid']] = hb['utime']
                    time.sleep(60)
                except Exception as er:
                    ci.logger.error(er)
        if not self.has_refresh_machine:
            self.has_refresh_machine=True
            thread=threading.Thread(target=load_data)
            thread.setDaemon(True)
            thread.start()


    def _get_product_uuid(self,ip):
        if len(ip)==36:
            uuid=ip
        else:
            uuid=self.GLOBAL_IP2UUID.get(ip,'')
        salt=self.GLOBAL_UUID2SALT.get(uuid,'')
        utime=self.GLOBAL_UUID2UTIME.get(uuid,'')
        if utime=='':
            utime=time.time()
        ret=[]
        if uuid=='' or salt=='':
            return self.hb.get_product_uuid(ip)
        else:
            ret.append({'uuid':uuid,'salt':salt ,'status':'online','utime':utime})
            return ret

    def _save_heartbeat_info(self,ip,uuid,salt):
        self.GLOBAL_IP2UUID[ip]=uuid
        self.GLOBAL_UUID2IP[uuid]=ip
        self.GLOBAL_UUID2SALT[uuid]=salt

    def flush_cache(self,req,resp):
        self.GLOBAL_IP2UUID={}
        self.GLOBAL_UUID2SALT={}
        self.GLOBAL_UUID2IP={}
        self.GLOBAL_UUID2UTIME={}
        return 'ok'


    def index(self,req,resp):
        return "ok"

    def help(self,req,resp):
        h='''
        ########## 远程执行 #################

        cli api -u user -c command -i ip -t timeout(second) --sudo 1 --token token \\
        --url_success http://yourservice.com/success --url_error http://yourservice.com/error
        例子:
        cli api -u test -c 'ps aux|grep java' -i 10.3.155.90 -t 30 --sudo 1 --token 0CF1F1AD-5784-4BCA-BCD1-F8F2CCB34719

        ########## 文件与shell ##############

        cli upgrade   更新 cli 程序
        cli shell -f filename -a "shell 参数"  下载并接行shell指令
        cli listfile   查看文件列表
        cli upload -f filename [-d directory] 上传文件
        cli download -f filename [-d directory] [-o path/to/save]  下载文件
        cli delfile -f filename -k key  删除文件

        ########## 环境变量 ##############

        cli addenv -k key -v value  -g group (default)  增加环境变量
        cli getevn  -k key -g group (default) 获取环境变量
        cli delenv   -k key -g group 删除环境变量
        cli listenv   -g group -e 1 查看某个组的环境变量 默认 default -e 1 导出
        cli updateenv   -k key -v value -g group (default)更新环境变量

        ########## CMDB ##############

        cli cmdb -t tag=value -f fields 按tag过滤cmdb中的数据,tag参考下面说明,参考下例
        cli cmdb  -t 'env=prod and ip=221.5.97.186'
             (tag 必须是 app_level,app_name,app_type,ip,belong_system,creator)
        cli select  -t 'app_type=java and ip=221.5.97.186' 取得cmdb中的IP,为批量作基础

         '''
        return h

    @auth
    def list_help(self, req, resp):
        l=[]
        for i in dir(self):
            if callable(getattr(self,i)):
                if not str(i).startswith('_'):
                    l.append(str(i))
        return l


    def _sys_log(self,req,params={},message=''):
        try:
            user=self._get_login_user(req)
            ip=self._client_ip(req)
            url=ci.local.env.get('PATH_INFO','')
            if len(params)==0:
                params=ci.local.env.get('param','{}')
            else:
                params=json.dumps(params)
            error_message=message
            ctime=int(time.time())
            fprefix=self.CHANNEL_FIELD_PREFIX
            sql='''INSERT INTO `%slog`
                        (
                         `%surl`,
                         `%sparams`,
                         `%smessage`,
                         `%sip`,
                         `%suser`,
                         `%stime`)
            VALUES (
                    '{url}',
                    '{params}',
                    '{message}',
                    '{ip}',
                    '{user}',
                    '{time}')
            '''%(self.CHANNEL_TABLE_PREFIX, fprefix,fprefix,fprefix,fprefix,fprefix,fprefix)
            data={'url':url,'params':params,'message':error_message,'ip':ip,'user':user,'time':ctime}
            ci.db.query(sql,data)
        except Exception as er:
            ci.logger.error(er)

    def feedback_result(self, req, resp):
        return self._proxy_go_server(req,resp,self._feedback_result,'/cli/feedback_result')

    def _feedback_result(self,req,resp):
        param=req.params['param']
        data=json.loads(param)
        if 'task_id' in data.keys() and str(data['task_id']) in ci.redis.smembers(self.TASK_LIST_KEY):
            # self.cmdkeys[str(data['index'])]=data['result']
            try:
                pl=ci.redis.pipeline()
                pl.setex(self.RESULT_KEY_PREFIX+ str(data['task_id']),60*5,json.dumps(data))
                dd={}
                dd['utime']=int(time.time())
                dd['task_id']=str(data['task_id'])
                if data['result']=='13800138000':
                    dd['result']='(error) time out'
                if 'error' in data.keys():
                    dd['result']=data['result']+ data['error']
                else:
                    dd['result'] = data['result']
                pl.lpush(self.RESULT_LIST_KEY,json.dumps(dd))
                pl.ltrim(self.RESULT_LIST_KEY,0,20000)
                pl.srem(self.TASK_LIST_KEY,str(data['task_id']))
                pl.execute()
            except Exception as er:
                print(er)
                ci.logger.error(er)
                pass
        ci.logger.info("task_id:%s,index:%s,ip:%s,result:\n%s"%(data['task_id'], str(data['index']), data['ip'],data['result']))

    def uuid(self,req,resp):
        return ci.uuid()

    def listclient(self,req,resp):
        return self.hb.listclient()

    def check_port(self, req,resp):
        param=req.params.get('param','{}')
        data=json.loads(param)
        host=data.get('h','')
        port=data.get('p','')
        if host=='':
            return '-h(host) is required'
        if port=='':
            return '-p(port) is required'
        if self._check_server(host,int(port)):
            return 'ok'
        else:
            return 'fail'

    def uninstall_cli(self, req, resp):
        params = self._params(req.params['param'])
        params['t']='status=online'
        params['o']='kvm,server'
        params['c']='inner_ip'
        req.params['param']=json.dumps(params)
        objs= self.getobjs(req,resp)
        ips=set()
        for obj in objs:
            if str(obj['inner_ip'][0]).strip()!='':
                ips.add(str(obj['inner_ip'][0]))
        req.params['param']=json.dumps({'s':'online'})
        _ips=set(map( lambda x:str(x), self.get_ip_by_status(req,resp).split(',')))
        return list(ips-_ips)


    def _check_server(self, address, port):
        import socket
        s = socket.socket()
        print "Attempting to connect to %s on port %s" % (address, port)
        try:
            s.settimeout(5)
            s.connect((address, port))
            print "Connected to %s on port %s" % (address, port)
            return True
        except socket.error, e:
            print "Connection to %s on port %s failed: %s" % (address, port, e)
            return False
        finally:
            try:
                s.close()
            except Exception as er:
                pass

    def md5(self,req,resp):
        params=self._params(req.params['param'])
        return ci.md5(params['s'])

    def del_etcd_key(self,req,resp):
        self._write_etcd( req.params['host']+req.params['key'],data={},method='DELETE')

    def _write_etcd(self,url,data={},method='PUT'):
        headers={'Authorization':self.ETCD_BASIC_AUTH}
        if method=='PUT':
            ret = requests.put(url, data=data, timeout=10, verify=False,headers=headers).json()
        elif method=='DELETE':
            ret = requests.delete(url, data=None, timeout=10, verify=False, headers=headers).json()


    def heartbeat(self,req,resp):
        client_ip=self._client_ip(req)
        uuid=''
        params=self._params(req.params['param'])
        if not 'uuid' in params.keys() or len(params['uuid'])!=36:
            return '(error) invalid uuid'
        else:
            uuid=params['uuid']
        if not 'ips' in params.keys():
           return '(error) invalid ips'
        ips=params['ips'].split(',')
        if not client_ip in ips:
            ci.logger.info(client_ip+' attack server ' + ','.join(ips) )
            # return '(error) invalid client_ip'
        if not 'hostname' in params.keys():
            params['hostname']='unknown'
        params['ip']=client_ip
        etcd = self.hb.getetcd(client_ip)
        try:
            url = "%s%s/heartbeat/%s/" % (etcd['server'][0], etcd['prefix'], params['uuid'])
            #self._write_etcd(url,data={'ttl':60*5,'value':','.join(ips)},method='PUT')
        except Exception as er:
            now = time.strftime('%Y-%m-%d %H:%M:%S')
            ci.redis.lpush(self.ERROR_KEY,json.dumps({'message':str(er),'function':'heartbeat','time':now}))
            ci.redis.ltrim(self.ERROR_KEY,0,500)
            ci.logger.error(er)


        p=ci.redis.pipeline()
        p.lpush(self.HEARTBEAT_LIST_KEY,json.dumps(params))
        if 'status' in params:
            try:
                if params['status']=='13800138000':
                    params['status']='{}'
                sys_status=json.loads(params['status'])
                sys_status['uuid']=params['uuid']
                sys_status['time']=time.time()
                status=json.dumps(sys_status)
                params['status']=status
                p.lpush(self.SYSTEM_STATUS_LIST_KEY,status)
                p.ltrim(self.SYSTEM_STATUS_LIST_KEY,0,5000)
            except Exception as er:
                params['status']='{}'
                pass
        p.ltrim(self.HEARTBEAT_LIST_KEY,0,5000)
        multi_ip_enable=ci.config.get('multi_ip_enable',False)
         #multi ip to single uuid
        if multi_ip_enable:
            for _i in ips:
               if _i!='' and (_i.startswith('10.') or _i.startswith('172.') or _i.startswith('192.')):
                   p.hset(self.HEARTBEAT_IP_MAP_UUID_KEY,_i,params['uuid'])
        #just use inner ip to uuid , reslove multi ip conflict ,but nat not support!
        else:
            p.hset(self.HEARTBEAT_IP_MAP_UUID_KEY, client_ip, params['uuid'])
        p.hset(self.HEARTBEAT_UUID_MAP_IP_KEY,params['uuid'],client_ip)
        p.execute()
        objs= self.hb.heartbeat(params)
        self._save_heartbeat_info(client_ip,uuid,objs['salt'])
        return objs

    def hb2db(self,req,resp):
        return  self._hb2db()

    def _hb2db(self):
        if self.has_hd2db:
            return 'ok'
        else:
            self.has_hd2db=True
        def _tmp():
            rows=[]
            batlen=20
            inner_timer=time.time()
            while True:
                try:
                    self._init_cmdb()
                    now=time.time()
                    snow=  time.strftime( '%Y-%m-%d %H:%M:%S',time.localtime(now))
                    js= ci.redis.lpop(self.HEARTBEAT_LIST_KEY)
                    fprefix = self.CHANNEL_FIELD_PREFIX
                    if js!=None  or len(rows)>0:
                        if js!=None:
                            row=json.loads(js)
                            rows.append(row)
                        if len(rows)>=batlen  or (len(rows)>0 and time.time()-inner_timer>3):
                            sqls=[]
                            ds=[]
                            sql='''
                            REPLACE INTO %sheartbeat
                                (%sUUID,
                                %shostname,
                                %sip,
                                %sutime,
                                `%sstatus`,
                                %ssystem_status
                                )
                                VALUES
                                ('{uuid}',
                                '{hostname}',
                                '{ip}',
                                '{utime}',
                                '{status}',
                                '{system_status}'
                                )
                            '''%(self.CHANNEL_TABLE_PREFIX,fprefix,fprefix,fprefix,fprefix,fprefix,fprefix)
                            for row in rows:
                                data={'uuid':row['uuid'],'status':'online','utime':snow,'hostname':row['hostname'],'ip':row['ip'],'system_status':row['status']}
                                ds.append(data)

                            ci.db.batch(sql,ds)
                            inner_timer=time.time()
                            rows=[]
                    else:
                        tbl_prefix=self.CHANNEL_TABLE_PREFIX
                        sql='''
                        INSERT INTO %shosts
                        (
                        `%suuid`,
                        %sip,
                        %shostname
                        )
                        SELECT %sheartbeat.`%suuid`,%sheartbeat.`%sip`,%sheartbeat.`%shostname` FROM %sheartbeat

                        LEFT JOIN %shosts ON %sheartbeat.%suuid=%shosts.%suuid

                        WHERE ISNULL( %shosts.%suuid)

                     ''' %(tbl_prefix,
                           fprefix,fprefix,fprefix,
                           tbl_prefix,fprefix,tbl_prefix,fprefix,tbl_prefix,fprefix,tbl_prefix,
                           tbl_prefix,tbl_prefix,fprefix,tbl_prefix,fprefix,
                           tbl_prefix,fprefix)
                        ci.db.query(sql)
                        time.sleep(10)
                except Exception as er:
                    ci.logger.error(er)
        threading.Thread(target=_tmp).start()
        return 'ok'

    def _parse_hd_for_influxdb(self,data):
        def get_key(dinput,pre=''):
            ilist = []
            type_input = type(dinput)
            if type_input == dict:
                for key in dinput.keys():
                    val = dinput[key]
                    ilist += get_key(val,pre+"."+key)
                return ilist
            if type_input == list:
                for index in range(len(dinput) ):
                    obj = dinput[index]
                    if type(obj) == dict or type(obj) == list:
                        ilist += get_key(obj,pre)
                    else:
                        ilist += get_key(obj,"%s.%s" % (pre,index) )
                return ilist
            if type_input != dict:
                ilist.append({'%s'%(pre):'%s'%(dinput)})
                return ilist
        data=get_key(data,'')
        kvs=dict()
        for kv in data:
            for k in kv.keys():
                kvs[k]=kv[k]
        return  kvs


    def hb2influxdb(self,req,resp):
        return self._hb2influxdb()

    def _hb2influxdb(self):
        from influxdb import InfluxDBClient
        if self.has_hb2influxdb:
            return 'ok'
        else:
            self.has_hb2influxdb=True
        conf=ci.config.get('influxdb',{})
        if 'app' in conf:
            del conf['app']
        client = InfluxDBClient(**conf)
        def _tmp():
            while True:
                try:
                    ret=ci.redis.rpop('system_status')
                    if ret!=None:
                        data=json.loads(ret)
                        json_body=[]
                        kvs=self._parse_hd_for_influxdb(data)
                        for kv in kvs:
                            val=0.0
                            if len(kv)>1:
                                key=kv[1:]
                            try:
                                val=round( float(kvs[kv]),3)
                            except Exception as er:
                                continue
                            row={
                                "measurement": "system_status",
                                "tags": {
                                    "uuid": kvs['.uuid'],
                                    'mtype':key,
                                    #"hostname": data['hostname'],
                                },
                                #"time": time.strftime( '%Y-%m-%d %H:%M:%S',time.localtime(data['time'])),
                                "fields": {
                                    "value":val,
                                }
                            }
                            json_body.append(row)

                        client.write_points(json_body)
                    else:
                        time.sleep(0.5)
                except Exception as er:
                    print(er)
                    pass
        threading.Thread(target=_tmp).start()
        return 'ok'

    def result2db(self,req,resp):
        return '(error)please run task'
        return self._result2db()



    def _result2db(self):
        if self.has_result2db:
            return 'ok'
        else:
            self.has_result2db=True
        def _tmp():
            rows=[]
            batlen=20
            inner_timer=time.time()
            while True:
                try:
                    self._init_cmdb()
                    now=time.time()
                    snow= time.strftime( '%Y-%m-%d %H:%M:%S',time.localtime(now))
                    js= ci.redis.rpop(self.RESULT_LIST_KEY)
                    fprefix = self.CHANNEL_FIELD_PREFIX
                    if js!=None or len(rows)>0:
                        if js!=None:
                            row=json.loads(js)
                            rows.append(row)
                        if len(rows)>=batlen or (len(rows)>0 and time.time()-inner_timer>3):
                            inner_timer=time.time()
                            update_sqls=[]
                            update_data=[]
                            insert_sqls=[]
                            insert_data=[]
                            insert_sql='''
                                    INSERT INTO %sresults
                                        (
                                        %stask_id,
                                        %scmd,
                                        %sresult,
                                        %sctime,
                                        %sop_user,
                                        %suuid
                                        )
                                        VALUES
                                        (
                                        '{task_id}',
                                        '{cmd}',
                                        '{result}',
                                        '{ctime}',
                                        '{op_user}',
                                        '{uuid}'
                                        )

                             ''' %(self.CHANNEL_TABLE_PREFIX,fprefix,fprefix,fprefix,fprefix,fprefix,fprefix)
                            update_sql='''


                                    UPDATE %sresults
                                        SET
                                        %sresult = '{result}' ,
                                        %sutime = '{utime}'
                                        WHERE
                                        %stask_id = '{task_id}'

                                '''%(self.CHANNEL_TABLE_PREFIX,fprefix,fprefix,fprefix)
                            for row in rows:
                                if 'user' in row:
                                    data={'op_user':row['user'],'ctime':row['ctime'],'cmd':row['cmd'],'task_id':row['task_id'],'uuid':row['uuid'],'result':''}
                                    insert_data.append(data)
                                else:
                                    data={'task_id':row['task_id'],'result':row['result'],'utime':row['utime']}

                                    update_data.append(data)

                            if len(insert_data)>0:
                                ci.db.batch(insert_sql,insert_data)
                            if len(update_data)>0:
                                ci.db.batch(update_sql,update_data)
                            # cnt=ci.redis.llen(self.RESULT_LIST_KEY)
                            # if cnt==None:
                            #     cnt=0
                            # if cnt>50:
                            #     batlen=int(cnt/5)
                            # else:
                            #     batlen=cnt
                            rows=[]
                    else:
                        time.sleep(1)
                except Exception as er:
                    ci.logger.error(rows)
                    ci.logger.error(er)
        threading.Thread(target=_tmp).start()
        return 'ok'


    def status(self,req,resp):
        return self.hb.status()

    @auth
    def offline(self,req,resp):
        return self.hb.offline()
    @auth
    def online(self,req,resp):
        return self.hb.online()

    def get_ip_by_status(self,req,resp):
        params=self._params(req.params.get('param','{}'))
        status='offline'
        if 's' in params:
            if params['s'] in ['offline','online']:
                status=params['s']
            else:
                return '-s(status) must be in "offline" or "online"'
        if status=='offline':
            rows= self.hb.offline()
        if status=='online':
            rows= self.hb.online()
        result=[]
        for row in rows:
            result.append(row['ip'])
        return ",".join(result)


    def dump_heartbeat(self,req,resp):
        self.hb.dump_data()
        return 'ok'

    @auth
    def suicide(self,req,resp):
        pass

    def _repair(self,ip):
        key_filename =ci.config.get('repair')['key_filename']
        password=ci.config.get('repair')['password']
        user=ci.config.get('repair')['user']
        port=ci.config.get('repair')['port']
        domain=ci.config.get('domain','127.0.0.1')
        cmd='sudo wget http://%s/cli/upgrade -O /bin/cli && sudo  chmod +x  /bin/cli && sudo  /bin/cli daemon -s restart' % (domain)
        return self._remote_exec(ip,cmd,user=user,password=password,port=port,key_file=key_filename)


    def repair(self,req,resp):
        port=ci.config.get('repair')['port']
        params=self._params(req.params.get('param','{}'))
        if 'ip' in params:
            ip=params['ip']
            return self._repair(ip)
        rows=self.hb.offline()
        ips=set()
        for row in rows:
            ips.add(str(row['ip']))
        ret=''
        import gevent
        import gevent.queue
        tqs= gevent.queue.Queue()
        ret=[]
        def task(tqs):
            while True:
                try:
                    if tqs.empty():
                        break
                    ip=tqs.get()
                    if self._check_server(ip,port):
                        ret.append("repair ip:"+ ip+"\n" +self._repair(ip))
                        ci.logger.info('repair ip:%s'%ip)
                    else:
                        ci.logger.info("server ip:%s down"%ip)
                        ret.append("server ip:%s down"%ip)
                except Exception as er:
                    ret.append("(error) repair ip:%s"%(ip))
                    ci.logger.error(er)
        map(lambda x:tqs.put(x),ips)
        tlen=tqs.qsize() if  tqs.qsize()<100 else 100
        threads = [gevent.spawn(task,tqs) for i in xrange(tlen)]
        gevent.joinall(threads)
        return "\n".join(ret)

    @auth
    def confirm_offline(self,req,resp):
        params=self._params(req.params['param'])
        if 'uuid' in params:
            return self.hb.confirm_offline(params['uuid'])
        else:
            return self.hb.confirm_offline()

    def _encode(self,plaintext,n=0,e=0,d=0):
        def _encryption(c,d,n):
            x = pow(c,d,n)
            return x
        result=[]
        result.append(str(n))
        result.append(str(d))
        for char in plaintext:
            result.append(str(_encryption(ord(char),e,n)))
        return base64.encodestring(','.join(result))

    def get_cmd(self,req,resp):
        params=self._params(req.params['param'])
        if 'uuid' in params and 'index' in params:
            # key= '%s%s%s'%( self.COMMNAD_PREFIX,params['uuid'],params['index'])
            key= '%s%s'%( self.COMMNAD_PREFIX,params['uuid'])
            ret=ci.redis.get(key)
            if 'host' in params and 'key' in params:
                def tmp(host,key):
                    self._write_etcd(host+key,data=None,method='DELETE')
                #tmp(params['host'],params['key'])
            if ret!=None:
                return json.loads(ret)
            else:
                return '{}'
        else:
            return 'invalid request'

    def _gen_ips(self,ips):
        sudo_ips = set()
        _sudo_ips = set(str(ips).split(','))
        for _sip in _sudo_ips:
            _ip_prefix = ''
            if _sip.rfind('.') > 0:
                _ip_prefix = _sip[0:_sip.rfind('.') + 1]
                if str(_sip).endswith('*'):
                    for i in range(1, 255):
                        sudo_ips.add(_ip_prefix + str(i))
                elif str(_sip).find('-') > 0:
                    _range = _sip[_sip.rfind('.') + 1:].split('-')
                    if len(_range) == 2:
                        for i in range(int(_range[0]), int(_range[1]) + 1):
                            sudo_ips.add(_ip_prefix + str(i))
                else:
                    sudo_ips.add(_sip)
        return list(sudo_ips)


    def _check_token_ip(self,req):
        params = self._params(req.params['param'])
        client_ip = self._client_ip(req)
        token = ci.local.env.get('HTTP_TOKEN', '') or params.get('token', '')
        key=self.AUTH_KEY_PREFIX+'%s_%s'%(client_ip,token)
        obj=ci.redis.get(key)
        if obj!=None:
            return  True,'ok'
        else:
            ci.logger.info('remote _check_token_ip '+ client_ip+ json.dumps(params))
            fprefix=self.CHANNEL_FIELD_PREFIX
            if token=='':
                return False, '(error)token is required(invalid request)'
            row=self.db.scalar("select * from %sauth where %stoken='{token}' limit 1"%(self.CHANNEL_TABLE_PREFIX,fprefix),{'token':token})
            if row==None or len(row)==0:
                return False, '(error)token not exist'
            if token!=row['%stoken'%(fprefix)]:
                return False, '(error)invalid token'
            if not client_ip  in str(row['%sip'%(fprefix)]).split(',') and client_ip!='127.0.0.1':
                return False, '(error)ip not in white list'
            ci.redis.set(key,params)
            return True,'ok'

    def _get_tokens(self,token=''):
        fprefix = self.CHANNEL_FIELD_PREFIX
        rows=[]
        token_str=ci.redis.get(self.TOKEN_LIST_KEY)
        if token_str!=None:
            rows=json.loads(token_str)
        else:
            rows = self.db.query("select %stoken,%sip,%suser,%ssudo,%ssudo_ips,%senv,%sblack_ips from %sauth" %
                                 (fprefix,fprefix,fprefix,fprefix,fprefix,fprefix,fprefix, self.CHANNEL_TABLE_PREFIX))
            if rows!=None and  len(rows)>0:
                ci.redis.set(self.TOKEN_LIST_KEY,json.dumps(rows))
            else:
                rows=[]
        if token!='':
            for row in rows:
                if row['%stoken'%(fprefix)]==token:
                    return row
            return []
        return rows

    def _set_token_lastupdate(self,token):
        try:
            fprefix = self.CHANNEL_FIELD_PREFIX
            self.db.query("update %sauth set %shit=%shit+1,%slast_update='{last_update}' where %stoken='{token}' limit 1"
                          % (self.CHANNEL_TABLE_PREFIX, fprefix, fprefix, fprefix, fprefix),
                          {'token': token, 'last_update': int(time.time())})
        except Exception as er:
            pass


    def flush_privileges(self,req,resp):
        ci.redis.delete(self.TOKEN_LIST_KEY)
        return 'ok'



    def api(self,req,resp):
        client_ip=self._client_ip(req)
        # self._init_cmdb()
        params=self._params(req.params['param'])
        ci.logger.info('remote execute api'+ client_ip+ json.dumps(params))
        token=ci.local.env.get('HTTP_TOKEN','') or params.get('token','')
        user=params.get('u','')
        check_permit=params.get('check_permit','0')
        sudo=False
        fprefix=self.CHANNEL_FIELD_PREFIX
        if not 'u' in params:
            return '-u(user) is required'
        if 'sudo' in params:
            sudo=True if params['sudo']=='1' or params['sudo']=='true' else False
        if token=='':
            return 'token is required(invalid request)'
        row=self._get_tokens(token)
        if row==None or len(row)==0:
            return '(error)token not exist'
        else:
            req.params['sudo']=str(row['%ssudo'%(fprefix)])
        if token!=row['%stoken'%(fprefix)]:
            return '(error)invalid token'
        if not client_ip  in str(row['%sip'%(fprefix)]).split(',') and client_ip!='127.0.0.1':
            return '(error)ip not in white list'
        if user!= str(row['%suser'%(fprefix)]):
            return '(error)invalid user'
        ip= params.get('i','')
        if ip=='':
            return '(error)invalid ip'
        ips=set(ip.split(','))
        sudo_ips=set()
        # sudo_ips=set(str(row['%ssudo_ips'%(fprefix)]).split(','))
        fblackips='%sblack_ips' % (fprefix)
        blackips=set()
        if fblackips in row:
            blackips=set(self._gen_ips(str(row[fblackips])))

        sudo_ips=set(self._gen_ips(str(row['%ssudo_ips'%(fprefix)])))
        validips=sudo_ips & ips
        unvalid_ips=ips-validips
        if (sudo and len(unvalid_ips)>0) and str(row['%ssudo_ips'%(fprefix)]).strip()!='*':
            return  '(error)ip not permit:'+ ','.join(unvalid_ips)
        _blacklist= ips & blackips
        if len(_blacklist)>0:
            return '(error) black ip not permit:' + ','.join(_blacklist)
        self._set_token_lastupdate(token)
        if str(row['%ssudo'%(fprefix)])!='1' and sudo:
            return '(error)sudo not permit'
        cmd=params.get('c','')
        p= {'cmd':cmd,'sudo':sudo}
        try:
            self.db.insert('%slog'%(self.CHANNEL_TABLE_PREFIX),{ '%surl'%(fprefix):'cli/api','%sparams'%(fprefix):json.dumps(p),
            '%suser'%(fprefix):user,'%stime'%(fprefix):int(time.time()),'%sip'%(fprefix):client_ip,'%smessage'%(fprefix):'API执行'})
        except Exception as er:
            ci.logger.error(er)
        if check_permit=='1':
            return 'ok'
        return self._proxy_go_server(req,resp,self._inner_cmd,'/cli/api')


    def _get_go_server(self,path_info=''):
        go_server = ci.config.get('go_server', '')
        if path_info=='':
            return go_server
        else:
            if go_server.startswith('http') and  not go_server.endswith('/'):
                go_server=go_server+'/'
            if len(path_info)>0 and path_info.startswith('/'):
                path_info=path_info[1:]
            return go_server+path_info

    def _proxy_go_server(self,req,resp,func,go_server_path_info):
        url=self._get_go_server(go_server_path_info)
        params = self._params(req.params['param'])
        if url=='':
            return func(req, resp)
        else:
            try:
                params['__client_ip__']=self._client_ip(req)
                resp= requests.post(url,data={'param':json.dumps(params)})
                if resp.status_code==200:
                    return resp.text
                else:
                    return func(req, resp)
            except Exception as er:
                ci.logger.error(er)
                return func(req, resp)





    def _cmd(self,ip,cmd,timeout=10,user='root',sudo=False,async="0",kw=None):
        if kw==None:
            kw={}
        try:
            if isinstance(ip,dict):
                if 'ip' in ip:
                    _ip=ip['ip']
                if 'uuid' in ip:
                    ip=ip['uuid']
            etcd=self.hb.getetcd(ip)
            # import urllib2,urllib
            # objs=self.hb.get_product_uuid(ip)
            objs=self._get_product_uuid(ip)
            salt=''
            puuid=''
            start=time.time()
            if objs==None  or len(objs)==0:
                return '(error) invalid ip'
            elif len(objs)==1:
                puuid=objs[0]['uuid']
                salt=objs[0]['salt']
                now=int(time.time())
                if objs[0]['status']=='offline' or  now-objs[0]['utime']>60*10:
                    return '(error) client status offline'
            elif len(objs)>1:
                return '(error) too many ip matched'

            if puuid=='' or salt=='':
                return '(error)client not online'
            #cmd=cmd.encode('utf-8')
            if sudo:
                pass
                # cmd=cmd.encode('utf-8')
            else:
                if user=='root':
                    return '(error) user root not permit'
                cmd=u"su '%s' -c \"%s\"" %(user, cmd.replace('"','\\"'))
            _timeout= timeout
            if _timeout>=10:
                _timeout=_timeout-2
            elif _timeout>=3:
                _timeout=_timeout-1
            data_raw={'cmd':cmd.encode('utf-8'),'md5': ci.md5(cmd.encode('utf-8') +str(salt)),'timeout':str(_timeout),'user':user}
            data_raw.update(kw)
            cmd_uuid=ci.md5( ci.uuid()+ ci.uuid() +str(random.random()) )
            ci.redis.setex('%s%s'%(self.COMMNAD_PREFIX,cmd_uuid),60*30,json.dumps(data_raw))
            ci.redis.sadd(self.TASK_LIST_KEY,cmd_uuid)
            #del data_raw['md5']
            data_raw['timeout']
            data_raw['task_id']=cmd_uuid
            data_raw['ctime']=int(start)
            data_raw['uuid']=ip
            data_raw['result']=''
            ci.redis.lpush(self.RESULT_LIST_KEY,json.dumps(data_raw))
            data={'value':json.dumps(data_raw) }
            #data={'value':cmd_uuid }


            # data=urllib.urlencode(data)
            url="%s%s/servers/%s/"%(etcd['server'][0],etcd['prefix'],puuid)
            # req = urllib2.Request(
            #         url =url,
            #         data=data
            # )
            # req.get_method = lambda: 'POST'
            # print urllib2.urlopen(req,timeout=10).read()
            # ret=json.loads(urllib2.urlopen(req,timeout=10).read())

            cert=ci.config.get('certificate',{})
            key_file=cert.get('key_file','/etc/cli/etcd-worker-key.pem')
            cert_file=cert.get('cert_file','/etc/cli/etcd-worker.pem')
            # ret=requests.post(url,data,timeout=10,verify=False,cert=( cert_file,key_file )).json()
            headers = {'Authorization': self.ETCD_BASIC_AUTH}
            ret=requests.post(url,data,timeout=10,verify=False,headers=headers).json()





            # print ret
            index=str(ret['node']['createdIndex'])
            self.cmdkeys[index]=''
            #ci.redis.sadd('indexs',index)
            # pl=ci.redis.pipeline()





            if async=='1':
                return cmd_uuid
            # if json.loads(ret['node']['value'])['cmd']==cmd:
            if True:




                # pl.execute()
                while True:
                    if (time.time()-start> timeout) or self.cmdkeys[index]!='':
                        #ci.redis.srem(self.TASK_LIST_KEY,index)
                        return '(error) timeout feedback results'
                        break
                    else:
                        time.sleep(0.5)
                        ret=ci.redis.get(self.RESULT_KEY_PREFIX+ cmd_uuid)
                        if ret!='' and ret!=None:
                            #ci.redis.srem(self.TASK_LIST_KEY,index)
                            try:
                                return ret.encode('utf-8')
                            except Exception as er:
                                # if isinstance(ret,basestring):
                                #     return json.dumps(ret)
                                return ret.decode('utf-8','ignore')
                return '(success) submit command success,timeout feedback reslt,job id:%s'% (cmd_uuid)
            else:
                return '(unsafe) submit command success '
        except Exception as er:
            print er
            ci.logger.error(er)
            return '(error)'+str(er.message)[0:80]


    def _is_while_ip(self,ip):
        wip=ci.config.get('white_ips',['127.0.0.1'])
        if ip in wip:
            return True
        else:
            return False
        pass

    def _is_web_while_ip(self,ip):
        wip=ci.config.get('web_white_ips',['127.0.0.1'])
        if ip in wip:
            return True
        else:
            return False
        pass


    def _client_ip(self,req):
        try:
            for i in ['HTTP_X_FORWARDED_FOR','HTTP_X_REAL_IP','REMOTE_ADDR']:
                if i in req.env.keys():
                    return req.env[i].split(',')[-1].strip()
        except KeyError:
            return req.env['REMOTE_ADDR']



    def get_cmd_result(self,req,resp):
        params=self._params(req.params['param'])
        if not 'k' in params.keys():
            return '-k(task_id) is required'
        return  ci.redis.get(self.RESULT_KEY_PREFIX+ str(params['k']))


    def _valid_cmd(self,cmd=''):
        keys=['shutdown','reboot','halt','poweroff','int','rm','kill']
        cmds=cmd.split('|')
        for c in cmds:
            cc=c.strip().split(" ")
            if len(cc)>0:
                if cc[0] in keys:
                    return False
                if cc[0]=='xargs':
                    for i in cc:
                        if i in keys:
                            return False
        return True


    def web_cmd(self,req,resp):
        client_ip=self._client_ip(req)

        #if not self._is_web_while_ip(client_ip):
        #    return '(error) ip is not in white list.'
        params=self._params(req.params.get('param','{}'))
        ci.logger.info('web_cmd client ip:'+ str(client_ip)+' param:'+ str(params))
        md5=params['md5']
        timestamp=params['ts']
        key=ci.config.get('web_key')
        if ci.md5(key+str(timestamp))!=md5:
            ci.logger.info('web_cmd attack'+ str(params))
            return '(error) sign error!'
        cmd=params.get('c','')
        blackList = ["'", '"', "\\", "`", ";", "$", "&", ">", "<"]
        blackList = ["\\", "`", ";", "$", ">", "<"]
        blackList = ["`",">", "<"]
        # blackList = [ "`",">"]
        if cmd!='':
            for a in blackList:
                if a in cmd:
                    return "-c(command) contains illegal characters"
        return self._inner_cmd(req,resp,True)

    @auth
    def cmd(self,req,resp):

        client_ip=self._client_ip(req)
        params=self._params(req.params['param'])
        ci.logger.info('remote cmd ip:%s,params:%s'%(client_ip,json.dumps(params)))
        op_user=ci.redis.get('login_'+req.env['HTTP_AUTH_UUID'])
        if not self._is_while_ip(client_ip):
            return '(error) ip is not in white list.'

        return self._inner_cmd(req,resp)


    def _inner_cmd(self,req,resp,web_cmd=False):
        client_ip=self._client_ip(req)
        op_user=''
        params=self._params(req.params['param'])
        cmd=''
        ip=''
        user='root'
        timeout=25
        async='0'
        out='text'
        sudo=False
        if  'c' in params:
            cmd=params['c']
        else:
            return '-c(cmd) require'
        if  'i' in params:
            if not web_cmd:
                ip=params['i']+','
            else:
                ip=params['i']
        else:
            return '-i(ip) require'
        if  't' in params:
            timeout= float( params['t'])
        if  'u' in params:
            user= params['u']
        # root_cmd=ci.config.get('root_cmd',False)
        # if not root_cmd and  user=='root':
        #     return "u(user) can't be root"
        if  'o' in params:
            out= params['o']
            if out not in ['json','text']:
                return '-o(output) must be text or json'
        if not self._valid_cmd(cmd):
            return '-c(cmd) is danger'
        if  'async' in params:
            async= params['async']
        if 'sudo' in params:
            sudo=True if params['sudo']=='1' or params['sudo']=='true' else False

        lg={'op_user':op_user,'from_ip':client_ip,'to_ip':ip,'user':user,'cmd':cmd}
        ci.logger.info(json.dumps(lg))
        result={}
        failsip=[]
        url_success=params.get('url_success','')
        url_error=params.get('url_error','')
        url = params.get('url', '')
        sys_user=params.get('sys_user','')
        feedback=params.get('feedback','1')
        # log_to_file = params.get('log_to_file', '1')
        kw={'url_success':url_success,'url_error':url_error,'sys_user':sys_user,'url':url,'feedback':feedback,'log_to_file':'1'}
        if feedback=='0':
            async='1'



        def task(tqs, cmd, timeout, user, sudo, async, kw):
            while True:
                if not tqs.empty():
                    i = tqs.get()
                    async='1'
                    result[i] = self._cmd(i, cmd, timeout=timeout, user=user, sudo=sudo, async=async, kw=kw)
                    #gevent.sleep(0)
                else:
                    break

        def cmd_to_result( result, timeout, user_async):
            if user_async == '0':
                start = time.time()
                total = len(result)
                if total > 1000:
                    gevent.sleep(0.5)
                else:
                    gevent.sleep(0.1)
                cc = 0
                _values=set()
                for _k, cmd_uuid in result.iteritems():
                    _values.add(cmd_uuid)

                while True:
                    if (time.time() - start > timeout) or cc == total:
                        break
                    for _k, cmd_uuid in result.iteritems():
                        if result[_k] in _values:
                            ret = ci.redis.get(self.RESULT_KEY_PREFIX + cmd_uuid)
                            if ret != '' and ret != None:
                                cc = cc + 1
                                # ci.redis.srem(self.TASK_LIST_KEY,index)
                                try:
                                    result[_k] = ret.encode('utf-8')
                                except Exception as er:
                                    # if isinstance(ret,basestring):
                                    #     return json.dumps(ret)
                                    result[_k] = ret.decode('utf-8', 'ignore')
                    if total-cc>100:
                        gevent.sleep(0.3)
                    else:
                        gevent.sleep(0.1)
                for _k, cmd_uuid in result.iteritems():
                    if result[_k] == None or (result[_k] in _values):
                        result[_k] = '(error) timeout feedback results'
                return result
            else:
                return result

        ip2uuid={}
        uuid2ip={}
        ipset=set()
        if web_cmd:
            import gevent
            import gevent.queue
            tqs= gevent.queue.Queue()
            ips=json.loads(ip)
            for x in ips:
                ip2uuid[x['ip']]=x['uuid']
                uuid2ip[x['uuid']]=x['ip']
                ipset.add(x['uuid'])
            map(lambda x:tqs.put(x),ipset)
            # tlen=tqs.qsize() if  tqs.qsize()<100 else 100
            threads = [gevent.spawn(task,tqs,cmd,timeout,user,sudo,async,kw) for i in xrange(2)]
            gevent.joinall(threads)
            result = cmd_to_result(result, timeout, async)

        elif ip.find(',')!=-1:
            self._load_uuid_info()
            import gevent
            import gevent.queue
            tqs= gevent.queue.Queue()
            ips=ip.split(',')

            uuid2ip=self.GLOBAL_UUID2IP
            ip2uuid=self.GLOBAL_IP2UUID
            uuids=self.GLOBAL_UUIDS

            for i in ips:
                if i in ip2uuid.keys():
                    # tqs.put(ip2uuid[i])
                    ipset.add(ip2uuid[i])
                else:
                    if len(i)==36:
                        # tqs.put(i)
                        ipset.add(i)
                    else:
                        failsip.append(i)
            # uuids=ci.redis.smembers("uuids")
            if uuids==None:
                uuids=set()
            failuuids=ipset-uuids
            ipset= ipset & uuids
            map(lambda x:tqs.put(x),ipset)
            threads = [gevent.spawn(task, tqs, cmd, timeout, user, sudo, async, kw) for i in xrange(2)]
            gevent.joinall(threads)
            result=cmd_to_result(result, timeout, async)

        else:
            result[ip]= self._cmd(ip,cmd,timeout=timeout,user=user,async=async)
            result = cmd_to_result(result, timeout, async)

        if out=='text':
            ret=[]
            for i in result:
                ret.append('-'*80)
                if len(i)<32 or len(uuid2ip)==0:
                    ret.append(i)
                else:
                    if i in uuid2ip:
                        ret.append(uuid2ip[i])
                    else:
                        ret.append(i)
                        failsip.append(i)
                try:
                    _t=json.loads(result[i])
                    ret.append(_t['result'])
                except Exception as er:
                    pass
                    ret.append(result[i])
            if len(failsip)>0:
                return "\n".join(ret)+"\nfails:\n"+"\n".join(failsip)
            return "\n".join(ret)
        elif out=='json':
            ret=[]
            for i in result:
                _result=result[i]
                if len(i)<32 or len(uuid2ip)==0:
                    _key=i
                else:
                    if i in uuid2ip:
                        _key=uuid2ip[i]
                    else:
                        _key=i
                        failsip.append(i)
                try:
                    _result=json.loads(_result)
                    ret.append({_key: _result})
                except Exception as er:
                    _result={'result':_result,'error':_result,'success':'','ip':i,'s':_key,'return_code':-1,'task_id':''}
                    ret.append({_key:_result})
            #ret.append({'failsip':','.join(failsip)})
            rets={'results':ret,'failsip':','.join(failsip)}
            return rets
        return result



    def cmdb(self,req,resp):
        params=self._params(req.params['param'])
        select='*'
        where=''
        if 'f' in params:
            select=params['f']
        if 't' in params:
            where=params['t']
        if where=='':
            return '-t(tag) is required'
        return self._cmdb_api(select.encode('utf-8'),where.encode('utf-8'))

    def load_cmdb(self,req,resp):
        fp='cmdb.json'
        if not os.path.exists(fp):
            fp='scripts/cmdb.json'
        with open(fp) as file:
            js=file.read()
            ci.redis.set('cmdb',json.dumps(json.loads(js)))
            return 'ok'

    def _init_cmdb(self):
        if self._cmdb==None:
            self._cmdb=ci.loader.cls("CI_DB")(**ci.config.get('cmdb'))


    def load_cmdb2db(self,req,resp):
        self._init_cmdb()
        ret=ci.redis.get('cmdb')
        if ret!=None:

            rows=json.loads(ret)
            sql='''

                REPLACE INTO %scmdb
                    (room,
                    business,
                    container,
                    module,
                    ip,
                    domain
                    )
                    VALUES
                    ('{room_en_short}',
                    '{business}',
                    '{container}',
                    '{module}',
                    '{ip}',
                    '{domain}'

                    )
                '''%(self.CHANNEL_TABLE_PREFIX)
            # self._cmdb.batch(sql,rows)
            for row in rows:
                try:
                    ci.db.query(sql,row)
                except Exception as er:
                    pass
            return 'ok'
        else:
            return '(error) cmdb is None'


    def _cmdb_options(self,type):
        ret=ci.redis.get(self.CMDB_OPTION_PREFIX+type)
        if ret!=None:
            return json.loads(ret)
        else:
            js=ci.redis.get('cmdb')
            rows=json.loads(js)
            t_set=set()
            for row in rows:
                if type in row and row[type]!=None and row[type]!='':
                    t_set.add(row[type])
            l_set=list(t_set)
            ci.redis.set(self.CMDB_OPTION_PREFIX+type,json.dumps(list(l_set)))
            return sorted(l_set)

    def cmdb_options(self,req,resp):
        params=self._params(req.params['param'])
        rows= self._cmdb_options(params['t'])
        ret=[]
        for val in rows:
            ret.append({'text':val,'value':val})
        return {'reply':ret}


    def _cmdb_api(self,select,where):
        js=ci.redis.get('cmdb')
        cmdb=json.loads(js)
        return ci.loader.helper('DictUtil').query(cmdb,select=select,where=where)

    def select(self,req,resp):
        params=self._params(req.params['param'])
        where=''
        if 't' in params:
            where=params['t']
        if where=='':
            return '-t(tag) is required'
        rows=self._cmdb_api('ip',where)
        rows=filter(lambda x:x['ip'].startswith('10.') or
                             x['ip'].startswith('172.16') or
                             x['ip'].startswith('192.168.'),rows )
        ips=set()
        map(lambda x:ips.add(x['ip']),rows)
        return ",".join(ips)



    def _get_login_user(self,req):
        opuser=ci.redis.get('login_'+ci.local.env.get('HTTP_AUTH_UUID','__nologin__'))
        return '' if opuser==None else opuser

    def _is_super_user(self,req):
        opuser=self._get_login_user(req)
        super_users=ci.config.get('super_users',['jqzhang'])
        if opuser in super_users:
            return True
        else:
            return False
    @auth
    def disableuser(self,req,resp):
        if not self._is_super_user(req):
            return '(error) user not permit'
        return self._userstatus(req.params['param'],0)

    @auth
    def enableuser(self,req,resp):
        if not self._is_super_user(req):
            return '(error) user not permit'
        return self._userstatus(req.params['param'],1)
    def _userstatus(self,param, status):
        # opuser=ci.redis.get('login_'+ci.local.env['HTTP_AUTH_UUID'])
        fprefix=self.CHANNEL_FIELD_PREFIX
        params=self._params(param)
        user=''
        uuid='(error) not login'
        if  'u' in params:
            user=params['u']
        else:
            return '-u(user) require'
        data={'user':user,'status':status}
        ci.db.query("update %suser set %sstatus='{status}' where %suser='{user}'"%(self.CHANNEL_TABLE_PREFIX,fprefix,fprefix),data)
        return 'success'


    def dispatch_cmd(self,req,resp):
        params=self._params(req.params['param'])
        if 'i' not in params:
             return '-i(ip) require'

        return 'ls /data';


    def _check_user(self,req,register=True):
        params=self._params(req.params['param'])
        user=''
        pwd=''
        opwd=''
        ip=''
        email=''
        if  'u' in params:
            user=params['u']
        else:
            return False, '-u(user) require'
        if  'p' in params:
            pwd=params['p']
        else:
            return False, '-p(password) require'

        if 'o' in params:
            opwd=params['o']
        if 'i' in params:
            ip=params['i']
        if 'e' in params:
            email=params['e']
        else:
            email=user
        return True,{'user':user,'pwd':pwd,'opwd':opwd,'ip':ip,'email':email}

    def register(self,req,resp):
        ok,data=self._check_user(req)
        fprefix = self.CHANNEL_FIELD_PREFIX
        if not ok:
            return data

        if data['opwd']!='':

            ok,msg=self._login(data['user'],data['opwd'],data['ip'])
            if ok:
                data['pwd']=ci.md5(data['pwd'])
                ci.db.query("update %suser set  %spwd='{pwd}',%sip='{ip}' where %suser='{user}'"%(self.CHANNEL_TABLE_PREFIX,fprefix,fprefix,fprefix),data)
                return 'success'
            else:
                return '-o(old password) is error'


        if ci.db.scalar("select count(1) as cnt from %suser where %suser='{user}'"%(self.CHANNEL_TABLE_PREFIX,fprefix),data)['cnt']>0:
            return "(error)user exist"
        data={'user':data['user'],'pwd':ci.md5(data['pwd']),'email':data['email']}
        ci.db.query("insert into %suser(%suser,%spwd,%semail) values('{user}','{pwd}','{email}')"%(self.CHANNEL_TABLE_PREFIX,fprefix,fprefix,fprefix),data)
        return 'success'


    def _login(self,user,pwd,ip):
        data={'user':user,'pwd':ci.md5(pwd)}
        fprefix = self.CHANNEL_FIELD_PREFIX
        is_exist=ci.db.scalar("select %sstatus from %suser where %suser='{user}' and %spwd='{pwd}' limit 1 offset 0"%(fprefix, self.CHANNEL_TABLE_PREFIX,fprefix,fprefix),data)
        udata={'user':user,'lasttime':time.strftime("%Y-%m-%d %H:%M:%S",time.localtime(time.time())),'ip':ip}
        if is_exist!=None:
            if is_exist['%sstatus'%(fprefix)]!=1:
                return False,'(error)user status disabled'
            ci.db.query("update %suser set %slogincount=%slogincount+1,%slasttime='{lasttime}',%sip='{ip}' where %suser='{user}'"%(self.CHANNEL_TABLE_PREFIX,fprefix,fprefix,fprefix,fprefix,fprefix),udata)
            return True,'success'
        else:
            ci.db.query("update %suser set %slogincount=%slogincount+1,%sfailcount=%sfailcount+1,%slasttime='{lasttime}',%sip='{ip}' where %suser='{user}'"%(self.CHANNEL_TABLE_PREFIX,fprefix,fprefix,fprefix,fprefix,fprefix,fprefix,fprefix),udata)
            return False,'(error) user or password is error'



    def login(self,req,resp):
        ok,data=self._check_user(req)
        if not ok:
            return data
        ok,msg=self._login(data['user'],data['pwd'],data['ip'])
        if ok:
            uuid=ci.uuid()
            ci.redis.setex('login_'+uuid,5*60,data['user'])
            return str(uuid)
        else:
            return msg


    def shell(self,req,resp):
        dir=req.params.get('dir','shell')
        file=req.params.get('file','')
        dir=dir.replace('..','').replace('.','').replace('/','')
        path= 'files'+ os.path.sep+ dir+ os.path.sep + file
        #ckey=self.FILE_CACHE_KEY_PREFIX+'_%s_%s'%(dir,file)
        if os.path.isfile(path):
            return open(path,'rb').read()
        else:
            try:
                content, ok = self._file_download(dir, file)
                print ok
                if ok:
                    #ci.redis.setex(ckey, 5 * 60, '1')
                    if not os.path.isdir(dir):
                        os.mkdir(dir, 0o744)
                    try:
                        open(path, 'wb').write(content)
                    except Exception as er:
                        ci.logger.error(er)
                    return content
            except Exception as er:
                ci.logger.error(er)
            return "#!/bin/bash\n echo '(error) file not found'"


    def upgrade(self,req,resp):
        if os.path.isfile('cli.mini'):
            return open('cli.mini').read()
        else:
            return open('cli').read()

    def _params(self,param='{}',opts=''):
        params= json.loads(param)
        return params

    def listfile(self,req,resp):
        params=self._params(req.params['param'])
        if 'd' in params:
            directory=params['d']
        else:
            directory=''
        directory=directory.replace('.','')

        atime = time.strftime('%Y-%m-%d %H:%M:%S')
        fprefix = self.CHANNEL_FIELD_PREFIX
        try:
            if directory!='':
                sql='''
                select %sfilename from %sfiles where `%suser` = '{dir}'
                GROUP  by %sfilename
                ''' % (fprefix,self.CHANNEL_TABLE_PREFIX,fprefix,fprefix)
            else:
                sql='''
                select %suser from %sfiles
                GROUP  by %suser
                ''' % (fprefix,self.CHANNEL_TABLE_PREFIX,fprefix)
            data = {'atime': atime, 'dir': directory}
            rows=ci.db.query(sql,data)
            ll=[]
            for row in rows:
                if directory=='':
                    ll.append(row['%suser'%(fprefix)])
                else:
                    fn=str(row['%sfilename' % (fprefix)].encode('utf-8','ignore'))
                    if fn.find('/')>0:
                        ll.append(fn[fn.rfind('/')+1:])
            return "\n".join(ll)

        except Exception as er:
            print er
            ci.logger.error(er)


        return "\n".join(os.listdir('files/'+directory))


    def download(self,req,resp):
        dir=req.params.get('dir','')
        file=req.params.get('file','')
        dir=dir.replace('.','')
        filepath='files/'+dir+'/'+file
        atime = time.strftime('%Y-%m-%d %H:%M:%S')
        fprefix = self.CHANNEL_FIELD_PREFIX
        sql='''
        select %surl from %sfiles where `%suser` = '{dir}' and %sfilename='{filename}' limit 1
        ''' % (fprefix,self.CHANNEL_TABLE_PREFIX,fprefix,fprefix)
        data = {'atime': atime, 'dir': dir, 'filename': filepath}
        row=ci.db.scalar(sql,data)
        url=''
        if row!=None and len(row)>0:
            url=row['%surl'%(fprefix)]
        sql='''
            UPDATE %sfiles
            SET
              `%satime` = '{atime}',
              `%shit` = `%shit`+1
            WHERE `%suser` = '{dir}' and %sfilename='{filename}'
            ''' %(self.CHANNEL_TABLE_PREFIX,fprefix,fprefix,fprefix,fprefix,fprefix)

        ci.db.query(sql,data)
        if not os.path.isfile(filepath):
            if url!='':
                print url
                content,ok=self._fastdfs_download(url)
                if ok:
                    open(filepath, 'wb').write(content)
                    with open(filepath, 'rb') as file:
                        resp.status = 200
                        resp.body = file.read()
                        return
                else:
                    resp.status = 404
                    resp.body = '(error) file not found'

            resp.status=404
            resp.body='(error) file not found'
        else:
            with open(filepath,'rb') as file:
                resp.body=file.read()

    def _file_download(self,dir,filename):
        dir=dir.replace('.','')
        filepath='files/'+dir+'/'+filename
        atime = time.strftime('%Y-%m-%d %H:%M:%S')
        fprefix = self.CHANNEL_FIELD_PREFIX
        sql='''
        select %surl from %sfiles where `%suser` = '{dir}' and (%sfilename='{filepath}' or %sfilename='{filename}') limit 1
        ''' % (fprefix,self.CHANNEL_TABLE_PREFIX,fprefix,fprefix,fprefix)
        data = {'atime': atime, 'dir': dir, 'filepath': filepath,'filename':filename}
        row=ci.db.scalar(sql,data)
        url=''
        if row!=None and len(row)>0:
            url=row['%surl'%(fprefix)]
        if url!='' and url.startswith('http'):
            return self._fastdfs_download(url)
        else:
            return None,False

    def _fastdfs_upload(self,filepath):
        conf=ci.config.get('fastdfs',{'upload_url':''})
        url=conf.get('upload_url','')
        data = {'file': open(filepath, 'rb')}
        result=requests.post(url, files=data).json()
        if result['retcode']=='0':
            return  conf.get('host','')+result['url']['file']
        return ''


    def _fastdfs_download(self, url):
        r=requests.get(url)
        if r.status_code==200:
            return r.content,True
        else:
            ci.logger.error('download url error'+ url)
        return None,False

    @auth
    @error_notify
    def upload(self,req,resp):

        user=self._get_login_user(req)
        file=req.params['file']
        filename=req.params['filename']
        fprefix = self.CHANNEL_FIELD_PREFIX
        ctime=time.strftime( '%Y-%m-%d %H:%M:%S')
        # directory=req.params.get('dir','/')
        directory=user
        directory=directory.replace('.','')
        url=''
        path='files/'+directory
        path=path.replace('///','/')
        path=path.replace('//','/')
        data = {'user': user, 'filename': filename, 'path': path, 'ctime': ctime, 'utime': ctime}
        filename=path+'/'+filename
        sql='''
        REPLACE INTO `%sfiles`
            (
             `%suser`,
             `%sfilename`,
             `%surl`,
             `%sctime`,
             `%sutime`)
        VALUES (
                '{user}',
                '{filename}',
                '{url}',
                '{ctime}',
                '{utime}')''' % (self.CHANNEL_TABLE_PREFIX,fprefix,fprefix,fprefix,fprefix,fprefix)
        self._sys_log(req,data, 'upload file %s' % filename)
        if not os.path.isdir(path):
            os.mkdir(path)
        def _upload(filename):
            try:
                return self._fastdfs_upload(filename)
            except Exception as er:
                ci.logger.error('upload fail:%s' % (filename))
                ci.logger.error(er)

        if not os.path.exists(filename):
            if isinstance(file,str):
                open(filename,'wb').write(file)
                url=_upload(filename)
            else:
                open(filename,'wb').write(file.file.read())
                url=_upload(filename)
            data = {'user': user, 'filename': filename, 'path': path, 'ctime': ctime, 'utime': ctime,'url':url}
            ci.db.query(sql,data)
            return 'success'
        else:
            return 'file exists'
    @auth
    def delfile(self,req,resp):
        params=self._params(req.params['param'])

        filename=''
        key='abc.com'
        directory='/'
        k=''
        if  'f' in params:
            filename=params['f']
        else:
            return '-f(filename) require'
        # if  'k' in params:
        #     k=params['k']
        # else:
        #     return '-k(key) require'
        # if not key==k:
        #     return 'key error'

        if  'd' in params:
            directory=params['d']
        self._sys_log(req, params, 'del file %s' % filename)
        directory=self._get_login_user(req)
        directory=directory.replace('.','')
        path='files/'+directory + '/' +filename
        if os.path.exists(path):
            os.remove(path)
            return "sucess"
        else:
            return "Not Found"

    @error_notify
    def rexec(self,req,resp):
        params=self._params(req.params['param'])
        ip=''
        cmd=''
        k=''
        key='Mz'
        user='root'
        password='root'
        port=22
        if 'i' in params:
            ip=params['i']
        else:
            return '-i(ip) require'
        if 'c' in params:
            cmd=params['c']
        else:
            return '-c(command) require'
        if  'k' in params:
            k=params['k']
        else:
            return '-k(key) require'
        if not key==k:
            return 'key error'
        if  'u' in params:
            user=params['u']
        if  'p' in params:
            password=params['p']
        if  'P' in params:
            port=params['P']
        return self._remote_exec(ip,cmd, user= user, password=password,port=port)

    def _remote_exec(self,ip,cmd,user='root',password='root',port=22,key_file=''):
        try:
            import paramiko
            ssh=paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

            if key_file!='':
                pkey= paramiko.RSAKey.from_private_key_file (key_file,password)
                try:
                      ssh.connect(ip,port=port,username=user,password=password,pkey=pkey)
                except Exception as err:
                      self.app.logger.error("PKERROR:"+str(err))
            else:
                ssh.connect(ip,port,user,password)
            ssh.exec_command('sudo -i',get_pty=True)
            ret=[]
            reterr=[]
            if isinstance(cmd,list):
               for c in cmd:
                   stdin, stdout, stderr = ssh.exec_command(cmd,get_pty=True)
                   reterr.append("".join(stderr.readlines()))
                   ret.append("".join(stdout.readlines()))
            else:
               stdin, stdout, stderr = ssh.exec_command(cmd,get_pty=True)
               reterr=stderr.readlines()
               ret=stdout.readlines()

            if len(reterr)>0:
                return "".join(reterr)
            else:
                return "".join(ret)
        except Exception as er:
            self.app.logger.error(er)
            return str(er)
        finally:
            try:
                ssh.close()
            except Exception as err:
                pass

################################################env###############################################
    def _checkenv(self,param):
        if isinstance(param,dict):
            params=param
        else:
            params=self._params(param)
        key=''
        fprefix=self.CHANNEL_FIELD_PREFIX
        group='default'
        if 'g' in params:
            group=params['g']
        if 'k' in params:
            key=params['k']
        else:
            return '-k(key) require'
        rows=ci.db.query("select * from %senv where `%sgroup_`='%s' and `%skey_`='%s'"% (self.CHANNEL_TABLE_PREFIX, fprefix,group,fprefix,key))
        if len(rows)>0:
            return True
        else:
            return False
    def listenvgroup(self,req,resp):
        params=self._params(req.params['param'])
        fprefix = self.CHANNEL_FIELD_PREFIX
        sql="select %sgroup_ from %senv group by %sgroup_"%(fprefix,self.CHANNEL_TABLE_PREFIX,fprefix)
        rows=ci.db.query(sql)
        ret=''
        for row in rows:
            if row['%sgroup_'%(fprefix)]!=None:
                ret+=str(row['%sgroup_'%(fprefix)])+"\n"
        return ret.strip()

        return ret
    def listenv(self,req,resp):
        params=self._params(req.params['param'])
        fprefix = self.CHANNEL_FIELD_PREFIX
        group='default'
        export='0'
        if 'g' in params:
            group=params['g']
        if 'e' in params:
            export=params['e']
        sql="select %skey_,%svalue_ from %senv where `%sgroup_`='%s'" % (fprefix,fprefix,self.CHANNEL_TABLE_PREFIX,fprefix, group)
        rows=ci.db.query(sql)
        if len(rows)==0:
            return '(error) not found'
        ret=''
        for row in rows:
            if export=='1':
                ret+='export '+row['%skey_'%(fprefix)]+'='+row['%svalue_'%(fprefix)]+"\n"
            else:
                ret+=row['%skey_'%(fprefix)]+'='+row['%svalue_'%(fprefix)]+"\n"

        return ret
    def updateenv(self,req,resp):
        params=self._params(req.params['param'])
        machine_id = ci.local.env.get('%s' % self.HEADER_MACHINE_ID, 'default')
        fprefix = self.CHANNEL_FIELD_PREFIX
        key=''
        value=''
        group=machine_id
        if 'k' in params:
            key=params['k']
        else:
            return '-k(key) require'
        if 'g' in params:
            group=params['g']
        if 'v' in params:
            value=params['v']
        else:
            return '-v(value) require'
        data={'%svalue_'%(fprefix):value,'%skey_'%(fprefix):key,'%sgroup_'%(fprefix):group}
        params['g'] = group
        if 'f' in params:
            if not self._checkenv(params):
                ci.db.insert('%senv' % (self.CHANNEL_TABLE_PREFIX), data)
        elif not self._checkenv(params):
            return '(error)key not is exsit'
        ci.db.update('%senv'%(self.CHANNEL_TABLE_PREFIX),{'%svalue_'%(fprefix):value},{'%skey_'%(fprefix):key,'%sgroup_'%(fprefix):group})
        return 'ok'

    def addenv(self,req,resp):
        params=self._params(req.params['param'])
        machine_id=ci.local.env.get('%s' % self.HEADER_MACHINE_ID,'default')
        fprefix = self.CHANNEL_FIELD_PREFIX
        key=''
        value=''

        group=machine_id
        if 'k' in params:
            key=params['k']
        else:
            return '-k(key) require'
        if 'g' in params:
            group=params['g']
        if 'v' in params:
            value=params['v']
        else:
            return '-v(value) require'
        if self._checkenv(req.params['param']):
            return '(error)key is exsit'
        data={'%skey_'%(fprefix):key,'%svalue_'%(fprefix):value,'%sgroup_'%(fprefix):group}
        ci.db.insert('%senv'%(self.CHANNEL_TABLE_PREFIX),data)
        self._sys_log(req,data)
        return 'ok'
    def delenv(self,req,resp):
        params=self._params(req.params['param'])
        machine_id = ci.local.env.get('%s' % self.HEADER_MACHINE_ID, 'default')
        fprefix = self.CHANNEL_FIELD_PREFIX
        key=''
        group=machine_id
        if 'g' in params:
            group=params['g']
        if 'k' in params:
            key=params['k']
        else:
            return '-k(key) require'
        self._sys_log(req,{'k':key,'g':group},'del env key %s'% key)
        params['g']=group
        if self._checkenv(params):
            ci.db.delete('%senv'%(self.CHANNEL_TABLE_PREFIX),{'%skey_'%(fprefix):key,'%sgroup_'%(fprefix):group})
            return 'ok'
        else:
            return '(error)key no found'
    def getenv(self,req,resp):
        params=self._params(req.params['param'])
        machine_id = ci.local.env.get('%s' % self.HEADER_MACHINE_ID, 'default')
        fprefix = self.CHANNEL_FIELD_PREFIX
        key=''
        group=machine_id
        if 'g' in params:
            group=params['g']
        if 'k' in params:
            key=params['k']
        else:
            return '-k(key) require'
        params['g']=group
        if not self._checkenv(params):
            return '(error)key no found'
        return ci.db.scalar("select %svalue_ from %senv where `%sgroup_`='%s' and `%skey_`='%s'"% (fprefix,self.CHANNEL_TABLE_PREFIX,fprefix,group,fprefix,key))['%svalue_'%(fprefix)]

################################################ doc ###############################################
    def _checkdoc(self,param):
        params=self._params(param)
        fprefix = self.CHANNEL_FIELD_PREFIX
        id=''
        if 'k' in params:
            id=params['k']
        else:
            return '-k(key) require'
        rows=ci.db.query("select * from %sdoc where `%sid`='%s'"% (self.CHANNEL_TABLE_PREFIX,fprefix, id))
        if len(rows)>0:
            return True
        else:
            return False
    def listdoc(self,req,resp):
        params=self._params(req.params['param'])
        fprefix = self.CHANNEL_FIELD_PREFIX
        if 'k' in params:
            return self.getdoc(req,resp)
        sql="select %scmd from %sdoc group by %scmd"%(fprefix, self.CHANNEL_TABLE_PREFIX,fprefix)
        rows=ci.db.query(sql)
        ret=''
        for row in rows:
            if row['%scmd'%(fprefix)]!=None:
                ret+=(row['%scmd'%(fprefix)].encode('utf-8'))+"\n"
        return ret


    def adddoc(self,req,resp):
        params=self._params(req.params['param'])
        fprefix = self.CHANNEL_FIELD_PREFIX
        cmd=''
        doc=''
        remark=''
        if 'c' in params:
            cmd=params['c']
        if 'd' in params:
            doc=params['d']
            if cmd=='':
                cmd=doc.strip().split(" ")[0]
        else:
            return '-d(document) require'
        if 'r' in params:
            remark=params['r']
        sql='''INSERT INTO %sdoc
            (
            %scmd,
            %sdoc,
            %sremark
            )
            VALUES
            (
            '{cmd}',
            '{doc}',
            '{remark}'
            )'''%(self.CHANNEL_TABLE_PREFIX,fprefix,fprefix,fprefix)
        ci.db.query(sql,{'cmd':cmd,'doc':doc,'remark':remark})
        #ci.db.insert('doc',{'cmd':cmd,'doc':doc,'remark':remark})
        return 'ok'
    def deldoc(self,req,resp):
        params=self._params(req.params['param'])
        fprefix = self.CHANNEL_FIELD_PREFIX
        id=''
        if 'k' in params:
            id=params['k']
        else:
            return '-k(id) require'
        if self._checkdoc(req.params['param']):
            ci.db.delete('%sdoc'%(self.CHANNEL_TABLE_PREFIX),{'%sid'%(fprefix):id})
            return 'ok'
        else:
            return '(error)key no found'
    def getdoc(self,req,resp):
        params=self._params(req.params['param'])
        fprefix = self.CHANNEL_FIELD_PREFIX
        key=''
        if 'k' in params:
            key=params['k']
        else:
            return '-k(keyword) require'
        if 'a' in params:
            rows= ci.db.query("select %sid,%sdoc from %sdoc where  `%scmd` like '%%%s%%' or %sdoc like '%%%s%%'"% (fprefix,fprefix, self.CHANNEL_TABLE_PREFIX,fprefix, key,fprefix, key))
        else:
            rows= ci.db.query("select %sid,%sdoc from %sdoc where  `%scmd`='%s'"% (fprefix,fprefix, self.CHANNEL_TABLE_PREFIX, fprefix, key))
        ret=''
        outid='i' in params
        for row in rows:
            if row['%sdoc'%(fprefix)]!=None:
                if outid:
                    ret+='# docid:  '+str(row['%sid'%(fprefix)])+"\n"+(row['%sdoc'%(fprefix)].encode('utf-8'))+"\n"*3
                else:
                    ret+=str(unicode.encode(row['%sdoc'%(fprefix)],'utf-8','ignore'))+"\n"*3
                #ret+="#"*50+"\n"
        return ret

################################################ tags ###############################################
    def addtag(self,req,resp):
        params=self._params(req.params['param'])
        fprefix = self.CHANNEL_FIELD_PREFIX
        table=''
        tag=''
        if 'tag' in params:
            tag=params['tag']
        else:
            return '--tag(tag) require'
        if 'object' in params:
            table=params['object']
        else:
            return '--object(object name) require'
        if tag.find('=')==-1:
            return 'tag must be "key=value"'
        body={}
        for t in tag.split(';'):
            kv=t.split('=')
            if len(kv)==2:
                body[kv[0]]=kv[1]
        row=ci.db.scalar("select %sid,%sbody from %stags where %stbname='{tbname}' limit 1 offset 0"%(fprefix,fprefix, self.CHANNEL_TABLE_PREFIX,fprefix),{'tbname':table})
        if row==None:
            data={'tbname':table, 'body':json.dumps(body)}
            ci.db.query("insert into %stags(%stbname,%sbody) values('{tbname}','{body}')"%(self.CHANNEL_TABLE_PREFIX,fprefix,fprefix),data)
        else:
            old=json.loads(row['%sbody'%(fprefix)])
            for k in body.keys():
                old[k]=body[k]
            data={'body':json.dumps(old),'id':row['%sid'%(fprefix)]}
            ci.db.query("update %stags set %sbody='{body}' where %sid='{id}'"%(self.CHANNEL_TABLE_PREFIX,fprefix,fprefix),data)
        return 'success'

    def listtag(self,req,resp):
        params=self._params(req.params['param'])
        fprefix = self.CHANNEL_FIELD_PREFIX
        rows=ci.db.query("select %stbname,%sbody from %stags"%(fprefix,fprefix, self.CHANNEL_TABLE_PREFIX))
        # return rows
        s=set()
        for row in rows:
            tags=json.loads(row['%sbody'%(fprefix)])
            for k in tags.keys():
                s.add('object_name: '+row['%stbname'%(fprefix)].encode('utf-8')+"\ttags: "+ k.encode('utf-8')+"=%s"% tags[k].encode('utf-8') )
        return "\n".join(s)


    def _check_body_val(self,table,key,value):
        fprefix = self.CHANNEL_FIELD_PREFIX
        row=ci.db.scalar("select %sbody from %stags where %stbname='%s' limit 1 offset 0"%(fprefix, self.CHANNEL_TABLE_PREFIX,fprefix,table))
        body={}
        if row!=None:
            body=json.loads(row['%sbody'%(fprefix)])
        else:
            return True,'OK'
        if key in body.keys():
            if body[key]!='':
                if value in body[key].split(','):
                    return  True,'OK'
                else:
                    return  False,"(error)value:'%s' must be in %s" %(key,str(body[key].encode('utf-8').split(',')))
            else:
                return True,'OK'
        else:
            return False,"(error)tag name must be in %s" %(str([ k.encode('utf-8') for k in body.keys()]))



# ################################################ objs ###############################################

    def _addobjs_items(self,obj_type, key,data):
        fprefix = self.CHANNEL_FIELD_PREFIX
        try:
            # ci.db.query("delete from %sobjs_items where `%suuid`='{key}' and %sotype='{type}'"
            #             %(self.CHANNEL_TABLE_PREFIX,fprefix,fprefix),{'type':obj_type,'key':key})
            insert_sql='''
            REPLACE INTO %sobjs_items
                (
                %sotype,
                %suuid,
                `%skey`,
                `%svalue`
                )
                VALUES
                (
                '{otype}',
                '{_key}',
                '{key}',
                '{value}'
                )
            '''%(self.CHANNEL_TABLE_PREFIX,fprefix,fprefix,fprefix,fprefix)
            insertdata=[]
            data=self._json2kv(data)
            for k,v in data.items():
                if not k in ['_key','_otype']:
                    insertdata.append({'otype':obj_type,'_key':key,'key':k,'value':v})
            if len(insertdata)>0:
                ci.db.batch(insert_sql,insertdata)
            ci.db.query("update %sobjs set %sstatus=1 where %sotype='{otype}' and `%skey`='{key}'"%
                        (self.CHANNEL_TABLE_PREFIX,fprefix,fprefix,fprefix),{'key':key,'otype':obj_type})
        except Exception as er:
            ci.logger.error(er)
            print(er)



    def _json2kv(self,data):
        def get_key(dinput, pre=''):
            ilist = []
            type_input = type(dinput)
            if type_input == dict:
                for key in dinput.keys():
                    val = dinput[key]
                    ilist += get_key(val, pre + "." + key)
                return ilist
            if type_input == list:
                for index in range(len(dinput)):
                    obj = dinput[index]
                    if type(obj) == dict or type(obj) == list:
                        ilist += get_key(obj, pre + "[%s]" % (index))
                    else:
                        ilist += get_key(obj, "%s[%s]" % (pre, index))
                return ilist
            if type_input != dict:
                ilist.append({'%s' % (pre): '%s' % (dinput)})
                return ilist

        data = get_key(data, '')
        kvs = dict()
        for kv in data:
            for k in kv.keys():
                if str(k).startswith('.'):
                    _k = str(k[1:]).strip()
                else:
                    _k=k
                kvs[_k] = kv[k].encode('utf-8','ignore').strip()
        return kvs

    @auth
    def check_objs(self,req,resp):
        results=[]
        fprefix = self.CHANNEL_FIELD_PREFIX
        rows=self.db.query("select %sbody,%skey from %sobjs where %sotype='%s'"%(fprefix,fprefix
                ,self.CHANNEL_TABLE_PREFIX,fprefix,self.OTYPE_CHECK_NAME))
        for row in rows:
            otype=row['%skey'%(fprefix)]
            ds = self.db.query("select %sbody,%skey from %sobjs where %sotype='%s'" % (fprefix, fprefix
                      , self.CHANNEL_TABLE_PREFIX,fprefix, otype))
            for d in ds:
                body=json.loads(d['%sbody'%(fprefix)])
                ok,message=self._check_otype_type(otype,body,row)
                if not ok:
                    body['_check_message_']=message
                    results.append(body)
        return results

    def repair_objs_items(self,req,resp):
        params = self._params(req.params['param'])
        if 'a' in params:
            threading.Thread(target=self._repair_objs_items,args=(True,)).start()
        else:
            threading.Thread(target=self._repair_objs_items, args=(False,)).start()
        return 'repair task has start running!'

    def _repair_objs_items(self,repair_all=False):
        fprefix = self.CHANNEL_FIELD_PREFIX
        rows=[]
        if repair_all:
            rows = ci.db.query(
            "select %sbody,%skey,%sotype from %sobjs" % (fprefix, fprefix, fprefix, self.CHANNEL_TABLE_PREFIX))
        else:
            rows = ci.db.query(
            "select %sbody,%skey,%sotype from %sobjs where %sstatus=0" % (fprefix, fprefix,fprefix, self.CHANNEL_TABLE_PREFIX,fprefix))
        pl = ci.redis.pipeline()
        for row in rows:
            pl.lpush( self.OBJS_LIST_KEY, json.dumps( {'otype':row['%sotype' % (fprefix)], 'key': row['%skey' % (fprefix)],
                             'data':   json.loads(row['%sbody' % (fprefix)])}))
        pl.execute()





    def _check_otype_type(self,otype,body,obj_define=None):
        fprefix = self.CHANNEL_FIELD_PREFIX
        if obj_define!=None:
            row=obj_define
        else:
            row=self.db.scalar("select %sbody from %sobjs where %sotype='%s' and `%skey`='%s'"%(fprefix,
                self.CHANNEL_TABLE_PREFIX,fprefix, self.OTYPE_CHECK_NAME,fprefix,otype))
        if row==None:
            row={}
            for k,v in body.items():
                if isinstance(v,dict):
                    row[k]='dict'
                elif isinstance(v,list):
                    row[k]='list'
            data={'%sbody'%(fprefix):json.dumps(row),'%skey'%(fprefix):otype,'%sotype'%(fprefix):self.OTYPE_CHECK_NAME}
            self.db.insert('%sobjs'%(self.CHANNEL_TABLE_PREFIX),data)
        else:
            if isinstance(row,str):
                row=json.loads(row)
            row=row['%sbody'%(fprefix)]
            if isinstance(row,str) or isinstance(row,unicode):
                row=json.loads(row)
            for k,v in body.items():
                if k in row.keys():
                    if row[k]=='dict' and not isinstance(v,dict):
                        return False,"(error) key '%s' must dict"%(str(k))
                    elif row[k]=='list' and not isinstance(v,list):
                        return False,"(error) key '%s' must list"%(str(k))
                else:
                    if isinstance(v, dict):
                        row[k] = 'dict'
                    elif isinstance(v, list):
                        row[k] = 'list'
            data = {'%sbody' % (fprefix): json.dumps(row)}
            where={'%skey' % (fprefix): otype,
                    '%sotype' % (fprefix): self.OTYPE_CHECK_NAME}
            if obj_define==None:
                self.db.update('%sobjs' % (self.CHANNEL_TABLE_PREFIX), data,where)
        return True,'ok'

    @error_notify
    def addobjs(self,req,resp):

        params=self._params(req.params['param'])
        fprefix = self.CHANNEL_FIELD_PREFIX
        tag=''
        ip=''
        otype='hosts'
        key=''
        name=''
        if 't' in params:
            tag=params['t']
        else:
            return '-t(tag) require'
        if 'i' in params:
            ip=params['i']
        # else:
        #     return '-i(ip) require'
        if 'o' in params:
            otype=params['o']
        else:
            return '-o(object type) require'
        if 'k' in params:
            key=params['k']
        else:
            key=ci.uuid()
        if 'n' in params:
            name=params['n']
        body={}
        try:
            if not isinstance(tag,dict):
                tag=json.loads(tag)
        except Exception as er:
            if tag.find('=') == -1:
                return 'tag must be "key=value"'
            pass

        if isinstance(tag,dict):# deal with json
            for k,v in tag.iteritems():
                ok, messege = self._check_body_val(otype, k, v)
                if not ok:
                    return messege.encode('utf-8')
                else:
                    body=tag
        else:

            for t in tag.split(';'):
                kv=t.split('=')
                if len(kv)==2:
                    ok,messege=self._check_body_val(otype,kv[0],kv[1])
                    if not ok:
                        return messege.encode('utf-8')
                    if re.match(r'^\[|\]$', str(kv[1].encode('utf-8','ignore'))):
                        body[kv[0]]=re.sub(r'^\[|\]$','',str(kv[1].encode('utf-8','ignore'))).split(',')
                    else:
                        body[kv[0]]=kv[1].encode('utf-8','ignore')
        body= json.loads(json.dumps(body).lower())
        ok,message=self._check_otype_type(otype,body)
        if not ok:
            return message

        self._addobjs(otype,body, ip, key, name)
        return 'success'

    def _addobjs(self,otype, body={}, ip='', name='', key='' ):
        if key=='':
            key=ci.uuid()
        if not isinstance(body,dict):
            return '(error) body must by dict data type'
        fprefix = self.CHANNEL_FIELD_PREFIX
        row = ci.db.scalar(
            "select %sid,%sbody,%sname,%skey from %sobjs where `%skey`='{key}' and %sotype='{otype}' limit 1 offset 0" % (
            fprefix, fprefix, fprefix, fprefix, self.CHANNEL_TABLE_PREFIX, fprefix, fprefix),
            {'key': key, 'otype': otype})
        if row == None:
            body['_key'] = key
            body['_otype'] = otype
            if not '_ctime' in body:
                body['_ctime']= time.strftime( '%Y-%m-%d %H:%M:%S')
            data = {'ip': ip, 'body': json.dumps(body), 'otype': otype, 'key': key, 'name': name, 'status': 0}
            # self._addobjs_items(otype,key,body)
            ci.redis.lpush(self.OBJS_LIST_KEY, json.dumps({'otype': otype, 'key': key, 'data': body}))
            ci.db.query(
                "insert into %sobjs(%sip,%sbody,%sotype,`%skey`,%sname,%sstatus) values('{ip}','{body}','{otype}','{key}','{name}','{status}')" % (
                self.CHANNEL_TABLE_PREFIX, fprefix, fprefix, fprefix, fprefix, fprefix, fprefix), data)
        else:
            old = json.loads(row['%sbody' % (fprefix)])
            key = row['%skey' % (fprefix)]
            old['_utime'] = time.strftime('%Y-%m-%d %H:%M:%S')
            for k in body.keys():
                old[k] = body[k]
            if name == '':
                name = str(row['%sname' % (fprefix)])
            data = {'ip': ip, 'body': json.dumps(old), 'id': row['%sid' % (fprefix)], 'name': name, 'status': 0}
            # self._addobjss_items(otype, key, old)


            ci.redis.lpush(self.OBJS_LIST_KEY, json.dumps({'otype': otype, 'key': key, 'data': old}))
            ci.db.query(
                "update %sobjs set %sip='{ip}',%sbody='{body}',%sname='{name}',%sstatus='{status}' where %sid='{id}'" % (
                self.CHANNEL_TABLE_PREFIX, fprefix, fprefix, fprefix, fprefix, fprefix), data)
        keys = ci.redis.smembers(self.GET_OBJS_KEY_GROUP)
        if keys != None and len(keys) > 0:
            pl = ci.redis.pipeline()
            for k in keys:
                pl.delete(k)
            pl.delete(self.GET_OBJS_KEY_GROUP)
            pl.execute()

    def listobjtype(self, req, resp):
        fprefix = self.CHANNEL_FIELD_PREFIX
        sql="select %sotype as otype from %sobjs group by %sotype"%(fprefix, self.CHANNEL_TABLE_PREFIX,fprefix)
        return ci.db.query(sql)


    def _build_dict_cache_key(self,data={}):
        l=data.keys()
        l.sort()
        key=[]
        for i in l:
            key.append('%s$$%s'%(str(i),str(data[i])))
        return  self.GET_OBJS_KEY_PREFIX+ '&'.join(key)

    @error_notify

    def getobjs(self,req,resp):
        params=self._params(req.params['param'])

        # cache_key=self._build_dict_cache_key(params)
        # cache_value=ci.redis.get(cache_key)
        # if cache_value!=None and cache_value!='none':
        #     return json.loads(ci.redis.get(cache_key))

        params.keys()
        fprefix = self.CHANNEL_FIELD_PREFIX
        otype=''
        tag=''
        cols='*'
        start=0
        limit=1000000
        count='0'
        cnt = 0
        otype_wheres=[]
        otype_where_str=''
        otypes=[]
        if 't' not in params:
            return '-t(tag) require'
        else:
            tag= params['t']
        if 'o' not in params:
            return '-o(object type) require'
        else:
            otype=params['o']
        if 'c'  in params:
            cols= params['c']
        if 'start' in params:
            start=int(params['start']);
        if 'count' in params:
            count='1'
        if 'limit' in params:
            limit=int(params['limit']);
        rows=[]
        inject_keyword=['insert ','update ','delete ',';']
        tag=tag.lower()
        for ijk in inject_keyword:
            if tag.find(ijk)!=-1:
                return '-t(tag) contains illegal characters'
        if self.MYSQL_VERSION=='':
            self.MYSQL_VERSION=self.db.scalar('select version() as version ')['version']
        if self.MYSQL_VERSION.startswith('5.7') or self.MYSQL_VERSION>'5.7':
            def _replace(s):
                s = s.group().strip()
                ops = ['<>', '=', '>', '<', ' like ', ' in ',' is null']
                for o in ops:
                    if s.find(o) > 0:
                        items = s.split(o)
                        items[1]=items[1].replace('"','').replace("'",'')
                        if items[0].find('[*]')>0:
                            if o==' like ':
                                return "NOT ISNULL(json_search(%sbody,'all','%%%s%%',NULL,'$.%s'))" % (fprefix, items[1].strip(), items[0].strip())
                            else:
                                return "NOT ISNULL(json_search(%sbody,'all','%s',NULL,'$.%s'))"%(fprefix, items[1].strip(),items[0].strip())
                        elif o == ' like ':
                            return "json_extract(%sbody,'$.%s') %s '%%%s%%'" % (fprefix, items[0], o, items[1].strip())
                        elif o == ' in ':
                            return "(json_contains(%sbody,'[\"%s\"]','$.%s'))" % (fprefix, items[0].strip(), items[1].strip())
                        elif o == ' is null':
                            return "isnull(json_length(json_extract(%sbody,'$.%s'))) or json_extract(%sbody,'$.%s')='' or json_length(json_extract(%sbody,'$.%s'))=0" % (fprefix, items[0],fprefix, items[0],fprefix,items[0])
                        else:
                            return "json_extract(%sbody,'$.%s') %s '%s'" % ( fprefix, items[0], o, items[1].strip())
            try:


                for _ot in otype.split(','):
                    otype_wheres.append("%sotype='%s' "%(fprefix,_ot))

                otype_where_str='(%s)'%(' or '.join(otype_wheres))

                if tag=='all':
                    if count=='1':
                        cnt = ci.db.scalar("select count(1) as cnt from %sobjs where %s and  %s" % (
                        self.CHANNEL_TABLE_PREFIX, otype_where_str, '1=1'))['cnt']
                    rows = ci.db.query("select * from %sobjs where %s and  %s limit %s,%s" % (self.CHANNEL_TABLE_PREFIX,otype_where_str, '1=1', start, limit))
                else:
                    ll=[]
                    ll.append(u'[\w\.]+\s*[=\<\>]+\s*[\w\.\:\-\u4e00-\u9fa5]+')
                    ll.append(u'[\w\.]+\s+like\s+[\w\.\:\-\u4e00-\u9fa5]+')
                    # ll.append(u'[\w\.]+\s+in\s+[\w\.\:\-\u4e00-\u9fa5]+')
                    ll.append(u'[\w\.\:\-\u4e00-\u9fa5\_]+\s+in\s+[\w\.]+')
                    ll.append(u'[\w\.]+\s+is\s+null')
                    ll.append(u'[\w\.]+\s*[=\<\>]+\s*[\'"][\w\.\:\-\s\u4e00-\u9fa5]+[\'"]')
                    ll.append(u'[\w\.]+\[\*\]\.[\w\.\:\-\s\u4e00-\u9fa5]+[=\<\>]+\s*[\w\.\:\-\u4e00-\u9fa5]+')
                    ll.append(u'[\w\.]+\[\*\]\.[\w\.\:\-\s\u4e00-\u9fa5]+\s+like\s+[\w\.\:\-\u4e00-\u9fa5]+')
                    where=re.sub('|'.join(ll),_replace,  tag)
                    if count=='1':
                        cnt = ci.db.scalar("select count(1) as cnt from %sobjs where %s and  %s " % (
                        self.CHANNEL_TABLE_PREFIX, otype_where_str, where))['cnt']
                    rows=ci.db.query("select * from %sobjs where %s and  %s limit %s,%s" % (self.CHANNEL_TABLE_PREFIX,otype_where_str, where,start,limit))
            except Exception as er:
                ci.logger.error(str(er)+ tag)
                print(er)
        else:
            try:
                rows=ci.db.query("select * from %sobjs where %sotype='{otype}'"%(self.CHANNEL_TABLE_PREFIX,fprefix),{'otype':otype})
            except Exception as er:
                ci.logger.error(str(er)+ tag)
        rows=map(lambda row:json.loads(row['%sbody'%(fprefix)]),rows)
        if self.MYSQL_VERSION.startswith('5.7') or self.MYSQL_VERSION>'5.7':
            rows= ci.loader.helper('DictUtil').query(rows,select=cols)
            if count=='1':
                rows= {'rows':rows,'count':cnt}
            else:
                pass
            if len(rows)>0 or rows!=None:
                # ci.redis.setex(cache_key, 3600*24 ,json.dumps(rows))
                # ci.redis.sadd(self.GET_OBJS_KEY_GROUP,cache_key)
                return rows
        else:
            return ci.loader.helper('DictUtil').query(rows,select=cols,where=tag)

    @error_notify
    def getobjs2(self, req, resp):
        params = self._params(req.params['param'])
        fprefix = self.CHANNEL_FIELD_PREFIX
        tprefix=self.CHANNEL_TABLE_PREFIX
        otype = ''
        tag = ''
        cols = '*'
        start = 0
        limit = 1000000
        count = '0'
        cnt = 0
        otype_wheres = []
        otype_where_str = ''
        otypes = []
        if 't' not in params:
            return '-t(tag) require'
        else:
            tag = params['t']
        if 'o' not in params:
            return '-o(object type) require'
        else:
            otype = params['o']
        if 'c' in params:
            cols = params['c']
        if 'start' in params:
            start = int(params['start']);
        if 'count' in params:
            count = '1'
        if 'limit' in params:
            limit = int(params['limit']);
        rows = []
        inject_keyword = ['insert ', 'update ', 'delete ', ';']
        tag = tag.lower()
        for ijk in inject_keyword:
            if tag.find(ijk) != -1:
                return '-t(tag) contains illegal characters'
        if self.MYSQL_VERSION == '':
            self.MYSQL_VERSION = self.db.scalar('select version() as version ')['version']
        if self.MYSQL_VERSION.startswith('5.7') or self.MYSQL_VERSION > '5.7' or True:
            def _replace(s):
                s = s.group().strip()
                ops = ['<>', '=', '>', '<', ' like ', ' in ', ' is null']

                for o in ops:
                    if s.find(o) > 0:
                        items = s.split(o)
                        items[1] = items[1].replace('"', '').replace("'", '\'').replace('(',"\(")
                        print items[0]
                        if items[0].find('[*]') > 0:
                            if o == ' like ':
                                return "(items.%skey like '%s' and items.%svalue like '%%%s%%')" % (
                                fprefix, items[0].strip().replace('*','%'),fprefix, items[1].strip())
                            elif o == ' is null':
                                return "(items.%skey like '%s' and ( items.%svalue='' or isnull(items.%svalue)))" % (
                                    fprefix, items[0].strip().replace('*','%'), fprefix, fprefix)
                            else:
                                return "(items.%skey like '%s' and items.%svalue %s '%s')" % (
                                fprefix, items[0].strip().replace('*','%'),fprefix,o, items[1].strip())
                        elif o == ' like ':
                            return "(items.%skey like '%s' and items.%svalue like '%%%s%%')"  % (fprefix, items[0].strip()+'%' ,fprefix , items[1].strip())
                        elif o == ' in ':
                            return "(items.%skey like '%s[%%]' and items.%svalue='%s')" % (fprefix, items[1].strip(),fprefix, items[0].strip())
                        elif o == ' is null':
                            return "(items.%skey='%s' and ( items.%svalue='' or isnull(items.%svalue)))" % (
                            fprefix, items[0], fprefix,  fprefix)
                        else:
                            return "(items.%skey='%s' and items.%svalue %s '%s')" % (fprefix, items[0],fprefix,o, items[1].strip())

            try:

                for _ot in otype.split(','):
                    otype_wheres.append("items.%sotype='%s' " % (fprefix, _ot.strip()))

                otype_where_str = '(%s)' % (' or '.join(otype_wheres))

                if tag == 'all':
                    if count == '1':
                        cnt = ci.db.scalar("select count(1) as cnt from %sobjs as items where %s and  %s" % (
                            self.CHANNEL_TABLE_PREFIX, otype_where_str, '1=1'))['cnt']
                    rows = ci.db.query("select * from %sobjs as items where %s and  %s limit %s,%s" % (
                    self.CHANNEL_TABLE_PREFIX, otype_where_str, '1=1', start, limit))
                else:
                    ll = []
                    ll.append(u'[\w\.]+\s*[=\<\>]+\s*[\w\.\:\-\u4e00-\u9fa5]+')
                    ll.append(u'[\w\.\*\[\]]+\s+like\s+[\w\.\:\-\u4e00-\u9fa5]+')
                    # ll.append(u'[\w\.]+\s+in\s+[\w\.\:\-\u4e00-\u9fa5]+')
                    ll.append(u'[\w\.\:\-\u4e00-\u9fa5\_]+\s+in\s+[\w\.]+')
                    ll.append(u'[\w\.]+\s+is\s+null')
                    ll.append(u'[\w\.]+\s*[=\<\>]+\s*[\'"][\w\.\:\-\s\u4e00-\u9fa5]+[\'"]')
                    ll.append(u'[\w\.]+\[\*\]\.[\w\.\:\-\s\u4e00-\u9fa5]+[=\<\>]+\s*[\w\.\:\-\u4e00-\u9fa5]+')
                    ll.append(u'[\w\.]+\[\*\]\.[\w\.\:\-\s\u4e00-\u9fa5]+\s+like\s+[\w\.\:\-\u4e00-\u9fa5]+')
                    where = re.sub('|'.join(ll), _replace, tag)
                    #print where
                    if count == '1':
                        cnt = ci.db.scalar('''select count(1) as cnt from ( SELECT objs.`%skey` FROM `%sobjs_items` AS  items
                        INNER JOIN `%sobjs` AS objs ON
                        items.`%sotype`=objs.`%sotype`
                        AND items.`%suuid`=objs.`%skey`
                        WHERE 1=1 and (%s) and %s
                        GROUP BY objs.%skey) ttt''' %(fprefix,tprefix,
                                                      tprefix,
                                                      fprefix,fprefix,
                                                      fprefix,fprefix,
                                                      otype_where_str,where,
                                                      fprefix) )['cnt']

                        #print ci.db.last_query()

                    rows = ci.db.query('''SELECT objs.`%skey`,objs.`%sbody` FROM `%sobjs_items`  AS  items
                        INNER JOIN `%sobjs` AS objs ON
                        items.`%sotype`=objs.`%sotype`
                        AND items.`%suuid`=objs.`%skey`
                        WHERE 1=1 and (%s) and %s
                        GROUP BY objs.%skey,objs.%sbody limit %s,%s''' %(fprefix,fprefix,tprefix,
                                                                         tprefix,
                                                                         fprefix,fprefix,
                                                                         fprefix,fprefix,
                                                                         otype_where_str,where,
                                                                         fprefix,fprefix,start,limit))
                    #print ci.db.last_query()
            except Exception as er:
                ci.logger.error(str(er) + tag)
                print(er)
        else:
            try:
                rows = ci.db.query(
                    "select * from %sobjs where %sotype='{otype}'" % (self.CHANNEL_TABLE_PREFIX, fprefix),
                    {'otype': otype})
            except Exception as er:
                ci.logger.error(str(er) + tag)
        rows = map(lambda row: json.loads(row['%sbody' % (fprefix)]), rows)
        if self.MYSQL_VERSION.startswith('5.7') or self.MYSQL_VERSION > '5.7':
            rows = ci.loader.helper('DictUtil').query(rows, select=cols)
            if count == '1':
                return {'rows': rows, 'count': cnt}
            else:
                return rows
        else:
            return ci.loader.helper('DictUtil').query(rows, select=cols, where=tag)

    @error_notify
    def delobjs(self,req,resp):
        params=self._params(req.params['param'])
        fprefix=self.CHANNEL_FIELD_PREFIX
        otype=''
        if 'o' not in params:
            return '-o(object type) require'
        else:
            otype=params['o']
        if 'k' in params:
            key=params['k']
        else:
            return '-k(unique key) require'
        cnt=ci.db.scalar("select count(1) as cnt from %sobjs  where `%skey`='{key}' and %sotype='{otype}'"%(self.CHANNEL_TABLE_PREFIX,fprefix,fprefix), {'key': key, 'otype': otype})['cnt']
        if cnt==0:
            return "(error) key %s not found"%(key)
        else:
            ci.db.query("delete from %sobjs  where `%skey`='{key}' and %sotype='{otype}'"%(self.CHANNEL_TABLE_PREFIX,fprefix,fprefix),{'key':key,'otype':otype})
            return 'success'


# ################################################ cron ###############################################

    def _cmdline_args(self,s):
        import re
        l= re.findall(r"'[\s\S]*[\']?'|\"[\s\S]*[\"]?\"",s,re.IGNORECASE|re.MULTILINE)
        for i,v in enumerate(l):
            s=s.replace(v,'{'+str(i)+'}')
        p=re.split(r'\s+',s)
        ret=[]
        for a in p:
            if re.match(r'\{\d+\}',a):
                a=l[int(re.sub(r'^{|}$','',a))]
            ret.append(a)
        return ret


    def _check_uuid(self,req):
        params=self._params(req.params['param'])
        ip=''
        if 'i' in params:
            ip=params['i']
        else:
            return False,'-i(ip or uuid) is required'
        #obj=self.hb.get_product_uuid(ip)
        obj=self._get_product_uuid(ip)
        if len(obj)==1:
            return True,obj[0]['uuid']
        else:
            return False,'client not online'



    def listcron(self,req,resp):
        ok,uuid=self._check_uuid(req)
        if ok :
            return self._cron(uuid,action='get')
        return uuid


    def statuscron(self,req,resp):
        ok,uuid=self._check_uuid(req)
        if ok :
            return self._cron(uuid,action='status')
        return uuid

    def stopcron(self,req,resp):
        ok,uuid=self._check_uuid(req)
        if ok :
            return self._cron(uuid,action='stop')
        return uuid
    def startcron(self,req,resp):
        ok,uuid=self._check_uuid(req)
        if ok :
            return self._cron(uuid,action='start')
        return uuid

    def loadcron(self,req,resp):
        ok,uuid=self._check_uuid(req)
        if ok :
            return self._cron(uuid,action='load')
        return uuid

    def addcron(self,req,resp):
        ok,uuid=self._check_uuid(req)
        if ok :
            params=self._params(req.params['param'])
            timer='* * * * *'
            args=[]
            cmd=''
            comment=''
            start=''
            out='/tmp/'+ci.uuid()+'.log'
            if not 't' in params:
                return '-t(timer) is required'
            if not 'c' in params:
                return '-c(cmd) is required'
            if 'a' in params:
                args=self._cmdline_args(params['a'])
            if 'o' in params:
                out=params['o']
            cmd=params['c']
            # timer=params['t']
            timer=timer.strip()
            cmd=cmd.strip()
            out=out.strip()
            job={'args':args,'start':'','cmd':cmd,'time':timer,'out':out}
            import urllib
            return self._cron(uuid,action='set?j=%s' % (  urllib.quote(json.dumps(job))) )
        return uuid

    def delcron(self,req,resp):
        ok,uuid=self._check_uuid(req)
        if ok :
            params=self._params(req.params['param'])
            if not 'k' in params.keys():
                return '-k(key) is required'
            k=params['k']
            return self._cron(uuid,action='del?h=%s'%k)
        return uuid

    def logcron(self,req,resp):
        ok,uuid=self._check_uuid(req)
        if ok :
            params=self._params(req.params['param'])
            if not 'd' in params.keys():
                return '-d(day) is required,for example: 20160607'
            d=params['d']
            return self._cron(uuid,action='log?d=%s'%d)
        return uuid


    def installcron(self,req,resp):
        ok,uuid=self._check_uuid(req)
        if ok :
            return self._cmd(uuid,'if [ ! -f  /bin/croncli ];then cli download -f croncli -o /bin/croncli ;fi && chmod +x /bin/croncli &&    /bin/croncli install &&   /bin/croncli start')
        return uuid

    def _cron(self,uuid,action='get',param=''):
        return self._cmd(uuid, "cli request --url '%s'" % ('http://127.0.0.1:4444/%s'% action) ,sudo=True)

    def log(self,req,resp):
        params = self._params(req.params['param'])
        ip= params.get('i','')
        try:
            n = int(params.get('n', '100'))
        except Exception as er:
            n=100
        n=str(n)
        if len(n)>3:
            return '-n(num) must be less then 1000'
        ret= self._cmd(ip, "tail -n %s /var/log/cli.log" %( n),kw={'log_to_file':'0'}, sudo=True)
        try:
            data=json.loads(ret)
            return data['result']
        except Exception as er:
            return ret


    def get_error(self,req,resp):
        result=[]
        while True:
            obj=ci.redis.lpop(self.ERROR_KEY)
            if obj==None:
                break
            else:
                result.append(obj)
        return result

    def check_status(self,req,resp):
        data={'db':'ok','etcd':'ok','redis':'ok'}
        # check db
        try:
            sum= ci.db.scalar('select md5(version()) as sum')['sum']
        except Exception as er:
            data['db'] = str(er)
            ci.logger.error(er)

        #check redis
        try:
            ci.redis.set('hello','world')
            world=ci.redis.get('hello')
            if world!='world':
                data['redis']='fail'
        except Exception as er:
            data['redis'] = str(er)
            ci.logger.error(er)
        #check etcd
        try:
            etcd=self.hb.getetcd('127.0.0.1')
            url = "%s%s/heartbeat/%s/" % (etcd['server'][0], etcd['prefix'], 'hello')
            self._write_etcd(url,{'hello':'world'})
        except Exception as er:
            data['etcd'] = str(er)
            ci.logger.error(er)
        return data

    def redis_cache(self,req,resp):
        params = self._params(req.params['param'])
        a=''
        k=''
        expire=60*60*12
        group=''
        if 'a' not in params:
            return '-a(action) is required'
        a = params.get('a', '')
        if 'g' in params:
            group=params.get('g','')
            group=str(group)+'_'
        else:
            return '-g(group) is required'
        if a not in ['keys','flush']:
            if not 'k' in params:
                return '-k(key) is required'
        if a not in ['set','get','keys','flush']:
            return '-a(action) is must be get or set or keys or flush'
        if group=='':
            return  '-g(group) is null'
        if 't' in params:
            try:
                expire=int(params['t'])
            except Exception as er:
                pass
        if a in ['set']:
            if 'v' not in params:
                return '-v(value) is required'
        v=params.get('v','{}')
        if a in ['set','get']:
            k=params.get('k','')
            if k=='':
                return '-k(key) is null'
        k=self.CACHE_KEY_PREFIX+str(group)+str(k)
        group=self.CACHE_KEY_PREFIX+str(group)
        try:
            if isinstance(v,dict) or isinstance(v,list):
                v=json.dumps(v)
            else:
                v=json.dumps(json.loads(v))
        except Exception as er:
            v=v
        if a=='set':
            if group!='':
                ci.redis.sadd(group,k)
            ci.redis.setex(k,expire,v)
            return 'ok'
        elif a=='get':
            v=ci.redis.get(k)
            try:
                v=json.loads(v)
                return v
            except Exception as er:
                return v
        elif a=='keys':
            return map(lambda x:x.replace(self.CACHE_KEY_PREFIX, ''), list(ci.redis.smembers(group)))
        elif a=='flush':
            ll=list(ci.redis.smembers(group))
            pl=ci.redis.pipeline()
            for i in ll:
                pl.delete(i)
            pl.delete(group)
            pl.execute()
            return 'ok'
        else:
            return "(error) '%s' not support"%(a)

    def google_code_sync(self,req,resp):
        ok, err = self._check_token_ip(req)
        if not ok:
            return {'message':err,'status':'fail'}
        ip = self._client_ip(req)
        params = self._params(req.params['param'])
        user=params.get('u','')
        platform=params.get('p','')
        secret_key=params.get('s','')
        if user=='':
            return {'message':'-u(user) is required','status':'fail'}
        if platform=='':
            return {'message':'-p(platform) is required','status':'fail'}
        if secret_key=='':
            return {'message': '-s(secret_key) is required', 'status': 'fail'}
        return self._google_code_add(ip,platform,secret_key,user,is_update_key=True)


    def _is_exist_google_key(self, user,platform):
        fprefix = self.CHANNEL_FIELD_PREFIX
        tprefix=self.CHANNEL_TABLE_PREFIX
        sql = '''
          SELECT COUNT(1) as cnt FROM `%sgoogle_auth` WHERE `%suser`={user} AND `%splatform`={platform}
        ''' % (tprefix, fprefix, fprefix)
        cnt = ci.db.scalar(sql, {'user': user, 'platform': platform})['cnt']
        if cnt > 0:
            return True,'user %s exist'% user
        else:
            return False,'user %s not exist'% user


    def is_exist_google_key(self, req, resp):
        ok,err=self._check_token_ip(req)
        import googauth
        if not ok:
            return err
        user=''
        platform=''
        ip=self._client_ip(req)
        params = self._params(req.params['param'])
        user=params.get('u','')
        platform=params.get('p','')
        if user=='':
            return {'message':'-u(user) is required','status':'fail'}
        if platform=='':
            return {'message':'-p(platform) is required','status':'fail'}
        ok,message=self._is_exist_google_key(user,platform)
        if ok:
            return {'status':'ok','message':'user exits','code':1}
        else:
            return {'status': 'ok', 'message': 'user not exits','code':0}



    def gen_google_auth(self, req, resp):
        ok,err=self._check_token_ip(req)
        import googauth
        if not ok:
            return err

        user=''
        platform=''
        ip=self._client_ip(req)

        params = self._params(req.params['param'])
        user=params.get('u','')
        platform=params.get('p','')
        if user=='':
            return {'message':'-u(user) is required','status':'fail'}
        if platform=='':
            return {'message':'-p(platform) is required','status':'fail'}
        secret_key = googauth.generate_secret_key()
        # code = googauth.generate_code(secret_key)
        # value = googauth.verify_time_based(secret_key, code)
        return self._google_code_add(ip, platform, secret_key, user)

    def _google_code_add(self, ip, platform, secret_key, user,is_update_key=False):
        fprefix = self.CHANNEL_FIELD_PREFIX
        tprefix=self.CHANNEL_TABLE_PREFIX
        now = time.strftime('%Y-%m-%d %H:%M:%S')
        data = {'user': user, 'platform': platform, 'ctime': now, 'utime': now, 'seed': secret_key,'status':1}
        ci.logger.info('gen_google_auth: %s' % (json.dumps({'ip': ip, 'user': user, 'platform': platform, 'now': now})))
        sql = '''
          SELECT COUNT(1) as cnt FROM `%sgoogle_auth` WHERE `%suser`={user} AND `%splatform`={platform}
        ''' % (tprefix, fprefix, fprefix)
        cnt = ci.db.scalar(sql, {'user': user, 'platform': platform})['cnt']
        if cnt > 0:
            if is_update_key:
                updatesql='''
                UPDATE `%sgoogle_auth`
                        SET
                          `%sseed` = '{seed}',
                          `%sutime` = '{utime}'
                        WHERE
                          `%suser` = '{user}' AND
                          `%splatform` = '{platform}'
                '''% (tprefix, fprefix, fprefix, fprefix, fprefix)
                ci.db.query(updatesql,data)
                key = self.GOOGLE_AUTH_KEY_PREFIX % (user, platform)
                ci.redis.set(key,json.dumps(data))
                return {'message': 'update user %s'% user, 'status': 'ok'}
            else:
                return {'message': '(error) user exist', 'status': 'fail'}
        inertsql = '''
        INSERT INTO `%sgoogle_auth`
            (
             `%sseed`,
             `%suser`,
             `%splatform`,
             `%sctime`,
             `%sutime`)
        VALUES (
                '{seed}',
                '{user}',
                '{platform}',
                '{ctime}',
                '{utime}');
        ''' % (tprefix, fprefix, fprefix, fprefix, fprefix, fprefix)
        ci.db.query(inertsql, data)
        url = 'https://chart.googleapis.com/chart?chs=200x200&chld=M|0&cht=qr&chl=otpauth%3A%2F%2Ftotp%2F' + platform + '%3Fsecret%3D' + secret_key
        img = self._qrcode(secret_key, 'image')
        term = self._qrcode('otpauth://totp/' + platform + '?secret=' + secret_key, 'term')
        return {'status': 'ok', 'message': secret_key, 'url': url, 'img': img, 'term': term}

    def verify_google_code(self, req, resp):
        import googauth
        fprefix = self.CHANNEL_FIELD_PREFIX
        tprefix = self.CHANNEL_TABLE_PREFIX
        ok, err = self._check_token_ip(req)
        if not ok:
            return err
        user = ''
        platform = ''
        ip=self._client_ip(req)
        params = self._params(req.params['param'])
        user = params.get('u', '')
        platform = params.get('p', '')
        code= params.get('c', '')
        if user == '':
            return {'message':'-u(user) is required','status':'fail'}
        if platform == '':
            return {'message':'-p(platform) is required','status':'fail'}
        if code == '':
            return {'message':'-c(code) is required','status':'fail'}
        now = time.strftime('%Y-%m-%d %H:%M:%S')
        ci.logger.info('verify_google_code: %s'%( json.dumps({'ip':ip,'user':user,'platform':platform,'now':now})))
        key = self.GOOGLE_AUTH_KEY_PREFIX % (user, platform)
        js= ci.redis.get(key)
        if js == None or js == 'null' or js == None:
            sql = '''
              SELECT `%sseed` as seed,`%sstatus` as status FROM `%sgoogle_auth` WHERE `%suser`={user} AND `%splatform`={platform}
            ''' % (fprefix,fprefix,tprefix, fprefix, fprefix)
            row = ci.db.scalar(sql, {'user': user, 'platform': platform})
            ci.redis.set(key,json.dumps(row))
        else:
            row=json.loads(js)

        if row!=None and len(row) > 0:
            secret_key=row['seed']
        else:
            return {'message':'(error) user not exist','status':'fail'}
        if row['status']==0:
            return {'message':'(error) user status diable','status':'fail'}
        data = {'user': user, 'platform': platform, 'ctime': now, 'utime': now, 'seed': secret_key}
        base=int( time.time()/30)
        codes=[]
        for i in range(base-5,base+5):
            codes.append( googauth.generate_code(secret_key,i))
        now=time.strftime( '%Y-%m-%d %H:%M:%S')
        data={'platform':platform,'user':user,'utime':now}
        if code in codes:
            sql = '''
            UPDATE `%sgoogle_auth` SET `%shit`=`%shit`+1 ,`%sutime`={utime} WHERE `%suser`={user} AND `%splatform`={platform}
            ''' % (tprefix, fprefix, fprefix, fprefix, fprefix, fprefix)
            try:
                ci.db.query(sql, data)
            except Exception as er:
                ci.logger.error(er)
            return {'message':'ok','status':'ok','data':secret_key}
        else:
            sql = '''
                UPDATE `%sgoogle_auth` SET `%sfail`=`%sfail`+1 ,`%sutime`={utime} WHERE `%suser`={user} AND `%splatform`={platform}
                ''' % (tprefix, fprefix, fprefix, fprefix, fprefix, fprefix)
            try:
                ci.db.query(sql, data)
            except Exception as er:
                ci.logger.error(er)
            return {'message':'fail','status':'fail'}


    def qrcode(self,req,resp):
        try:
            import pyqrcode
        except Exception as er:
            return 'pyqrcode module not found'
        params = self._params(req.params.get('param', '{}'))
        if len(params)>0:
            code=params.get('code', '')
            type=params.get('type', 'term')
            scale=params.get('scale', 8)
        else:
            code=req.params.get('code', '')
            type=req.params.get('type', 'html')
            scale=req.params.get('scale', 8)
        try:
            scale=int(scale)
        except Exception as er:
            scale=8
        return self._qrcode(code,type,scale)

    def _qrcode(self, code, type='term',scale=8):
        import pyqrcode
        if code == '':
            return 'code is require'
        qr=pyqrcode.create(code)
        if type == 'html':
            return '<html><body><img src="data:image/png;base64,%s"></body></html> ' % (qr.png_as_base64_str(scale,quiet_zone=1))
        elif type=='image':
            return '<img src="data:image/png;base64,%s"> ' % (qr.png_as_base64_str(scale,quiet_zone=1))
        elif type == 'term':
            return qr.terminal(quiet_zone=1)
        else:
            return "type must in '%s'"%(','.join(['html','image','term']))

    def vm(self,req,resp):
        ok, err = self._check_token_ip(req)
        if not ok:
            return err
        params = self._params(req.params['param'])

        def _uuid(phy_ip,ip):
            ip_12=''.join([i[0:3] for i in [i + 'aa' for i in ip.split('.')]])
            phy_ip_12=''.join([i[0:3] for i in [i + 'aa' for i in phy_ip.split('.')]])
            hour = time.strftime('%Y%m%d%H')
            _id=phy_ip_12+hour+ip_12
            return _id[0:8] + '-' + _id[8:12] + '-' + _id[12:16] + '-' + _id[16:20] + '-' + _id[20:32]

        action=''
        phy_ip=''
        async="0"
        if 'async' in params.keys() and (params['async']=='1' or params['async']=='true'):
            async="1"
        if 't' not in params.keys():
            return '(error) -t(tag) is required,tag must be json format'
        if isinstance(params['t'],unicode) or isinstance(params['t'],str):
            params['t']=json.loads(params['t'])
        if 't' in params.keys():
            if isinstance(params['t'],unicode) or isinstance(params['t'],str):
                params['t']=json.loads(params['t'])
            if not 'action' in params['t']:
                return '(error) action is required'
            action=params['t']['action']
        actions=['create','stop','start','undefine']
        if action not in actions:
            return "(error) action must by in %s" % (','.join(actions))
        if action in ['create']:
            for key in ['ip','phy_ip','vm_type']:
                if  key not in params['t'].keys():
                    return '(error) %s is required'%(key)
            if not 'uuid' in params['t'].keys():
                params['t']['uuid']=_uuid(params['t']['phy_ip'],params['t']['ip'])
        if action in ['stop','start']:
            for key in ['uuid','phy_ip']:
                if  key not in params['t'].keys():
                    return '(error) %s is required'%(key)
        task_id=ci.uuid()
        phy_ip=params['t']['phy_ip']
        cache_key=self.CACHE_KEY_PREFIX+ self.VM_TASK_KEY_GROUP+'_'+task_id
        ci.redis.setex(cache_key,60*60*24,json.dumps(params['t']))
        phy_uuid=ci.redis.hget(self.HEARTBEAT_IP_MAP_UUID_KEY,phy_ip)
        vmid=ci.uuid()
        self._addobjs(otype= 'vm', body= params['t'])
        if phy_uuid==None or str(phy_uuid)=='':
            return '(error) invalid phy_ip'
        return self._cmd({'uuid':phy_uuid},"cli shell -f vm -d jqzhang -a '%s'"%(task_id),
                         timeout=60*20,sudo=True,async=async)


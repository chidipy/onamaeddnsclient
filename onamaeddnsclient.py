#!/usr/bin/python3 -u
# -*- coding: utf-8 -*-

#--------------------------------------------------------------------#
# onamaeddnsclient.py  Ver. 1.0.1(2020/10/24)                        #
#   お名前.com ダイナミックDNS クライアント(複数ドメイン対応版)      #
#     Copyright (C) 2020 chidipy  http://chidipy.jpn.com/            #
#--------------------------------------------------------------------#

#--------------------------------------------------------------------#
# 設定                                                               #
#--------------------------------------------------------------------#
# お名前.comのユーザ名、パスワード
USERID=""
PASSWORD=""

# ドメインリスト
# -書式-
#   ホスト名 ドメイン名,ホスト名 ドメイン名
#    (ホスト名とドメイン名間はスペース区切り、レコード(ホスト名、ドメイン名のセット）はカンマ区切り)
# -例-
#   example.com
#   wwww example.com
#   wwww example.com,blog example.com,wwww xxxx.com
DOMAINLIST=""

# 強制的にDDNSを更新する日数間隔（無効にする場合は大きい数字にしてください）
DAYS_FORCE_UPDATE=1

# ログの出力パス
PATH_LOG="/var/log/onamaeddnsclient.log"

# 前回IPアドレスと最終更新日時を記録するファイル
PATH_PRECHANGE="/var/lib/onamaeddnsclient.txt"

# 冗長ログ出力(False/True)
LOG_VERBOSE=False

#--------------------------------------------------------------------#
# 定数                                                               #
#--------------------------------------------------------------------#
LOGLEVEL_INFO="INFO"
LOGLEVEL_WARN="WARN"
LOGLEVEL_ERROR="ERROR"

SUCCESSMSG="000 COMMAND SUCCESSFUL"

#--------------------------------------------------------------------#
# モジュール読み込み                                                 #
#--------------------------------------------------------------------#
import sys
import requests
import fcntl
import os
import re
from datetime import datetime,date,timedelta
import socket
import ssl

#--------------------------------------------------------------------#
# 関数                                                               #
#--------------------------------------------------------------------#
def write_log(msg,level="DEBUG"):
    flag_writable=True
    # メッセージ組み立て
    output="{0} {1:<5} {2}".format(str(datetime.now()) ,level,msg)
    if os.access(os.path.dirname(PATH_LOG),os.W_OK) == False:
        flag_writable=False
    if os.path.exists(PATH_LOG)==True:
        if os.access(PATH_LOG,os.W_OK) == False:
            flag_writable=False
    if flag_writable==False:
        sys.stderr.write("LOGGING ERROR!:"+output)
        return
    
    try:
        file_output = open(PATH_LOG,"a",encoding='utf-8')
        fcntl.flock(file_output,fcntl.LOCK_SH)
        file_output.write(output+"\n")
        fcntl.flock(file_output,fcntl.LOCK_UN)
        file_output.close()
    except:
        (exc_type,exc_value,exc_traceback)=sys.exc_info()
        print(output)
        print("Failed to write log. path:{} reason:{}".format(PATH_LOG,str(exc_value)))
        

def get_globalip_inetip():
    gip=None
    errmsg=None
    
    try:
        response=requests.get('http://inet-ip.info/ip')
    except:
        (exc_type,exc_value,exc_traceback)=sys.exc_info()
        errmsg = "Faild to get global ip address. reason:" + str(exc_value)
        return gip,errmsg
    
    if response.status_code != 200 :
        errmsg = "Faild to get global ip address. status_code:" + str(response.status_code)
        return gip,errmsg
    
    gip=response.text
    
    return gip,errmsg

def get_globalip_dyndns():
    gip=None
    errmsg=None
    
    try:
        response=requests.get('http://checkip.dyndns.com/')
    except:
        (exc_type,exc_value,exc_traceback)=sys.exc_info()
        errmsg = "Faild to get global ip address. reason:" + str(exc_value)
        return gip,errmsg
    
    if response.status_code != 200 :
        errmsg = "Faild to get global ip address. status_code:" + str(response.status_code)
        return gip,errmsg
    
    html=response.text
    gip=html.split(':')[1].strip().rstrip('</body></html>\r\n')
    
    return gip,errmsg



def get_globalip():
    gip=None
    errmsg=None
    
    (gip,errmsg)=get_globalip_inetip()
    if errmsg != None :
        write_log("inetip:" + errmsg,LOGLEVEL_WARN)
    else:
        return gip,errmsg
        
    (gip,errmsg)=get_globalip_dyndns()
    if errmsg != None :
         write_log("dyndns:" + errmsg,LOGLEVEL_WARN)
    else:
        return gip,errmsg
    
    return gip,errmsg

def get_prechange(path_history):
    preip=None
    prechange=None
    dt_timestamp=None
    errmsg=None
    
    # 履歴ファイル存在確認
    if os.path.exists(path_history) == False:
        # 存在しない場合は初回
        return "",datetime.strptime("1970-01-01 00:00:00",'%Y-%m-%d %H:%M:%S'),errmsg

    if os.access(path_history,os.R_OK) == False:
        errmsg="The file does not exist or does not have read permission. path:" + path_history
        
        return preip,dt_timestamp,errmsg
    
    try :
        fh = open(PATH_PRECHANGE,"r",encoding='utf-8')
    except:
        (exc_type,exc_value,exc_traceback)=sys.exc_info()
        errmsg = "Faild to open file. path:{} reason:{}".format(PATH_LOG,str(exc_value))
        return preip,dt_timestamp,errmsg

    for getline in fh:
        regexp=r'^([^\t]+?)\t(.+?)$'
        try:
            pattern=re.compile(regexp)
        except:
            (exc_type,exc_value,exc_traceback)=sys.exc_info()
            errmsg = "Faild to regexp compile. regexp:{} reason:{}".format(regexp,str(exc_value))
            return preip,dt_timestamp,errmsg

        match=pattern.search(getline)
        if match != None:
            preip=match.group(1)
            str_timestamp=match.group(2)
            dt_timestamp=datetime.strptime(str_timestamp,'%Y-%m-%d %H:%M:%S')

        break

    fh.close()
    
    if preip=="" or preip == None or str_timestamp == "" or str_timestamp == None :
        errmsg="Failed to get ip address or change timestamp."
        return preip,dt_timestamp,errmsg

    return preip,dt_timestamp,errmsg

def update_ip(ip,domainname,hostname,userid,password):
    errmsg = None

    # 送信文生成
    senddata = '''LOGIN
USERID:{userid}
PASSWORD:{password}
.
MODIP
HOSTNAME:{hostname}
DOMNAME:{domainname}
IPV4:{ip}
.
LOGOUT
.'''.format(userid=userid, password=password, hostname=hostname,domainname=domainname, ip=ip)

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            # タイムアウト5秒
            sock.settimeout(5)
            # SSLソケット作成
            sslsock=ssl.wrap_socket(sock)
            # 接続
            sslsock.connect(("ddnsclient.onamae.com", 65010))
            # "000 COMMAND SUCCESSFUL"が返ってくるのを待つ
            res=sslsock.recv(1024)
            if SUCCESSMSG not in res.decode() :
                errmsg="Failed to connect. response:{0}".format(res.decode())
                return errmsg

        # 改行でリスト化
            listsenddata=senddata.split("\n")
            sendcommand=""
            for line in listsenddata:
                # バイト列化
                byteline=line.encode() + b'\r\n'
                # 命令1行を送信
                sslsock.sendall(byteline)
                sendcommand = sendcommand + " " + line
                if line == ".":
                    # "000 COMMAND SUCCESSFUL"が返ってくるのを待つ
                    res=sslsock.recv(1024)
                    if SUCCESSMSG not in res.decode() :
                        errmsg="Failed to command. response:{0} command:{1}".format(res.decode(),sendcommand)
                        return errmsg
                    else:
                        sendcommand=""
        except:
            (exc_type,exc_value,exc_traceback)=sys.exc_info()
            errmsg = "Faild to update ip address. reason:{0}".format(str(exc_value))
            return errmsg

        # with文なのでソケットは自動的にcloseする
    return errmsg
        

def update_ip_all(ip_new,domainlist,userid,password):
    errmsg = None 
    flag_success = False

    # カンマ区切りの文字列をリスト可
    listdomain=domainlist.split(',')
    for strhostdomain in listdomain:
        # ホスト名とドメイン名に分離]
        listhostdomain=strhostdomain.split(' ')
        try:
            if len(listhostdomain) > 1:
                hostname=listhostdomain[0]
                domainname=listhostdomain[1]
            else:
                hostname = ""
                domainname = listhostdomain[0]
        except:
            (exc_type,exc_value,exc_traceback)=sys.exc_info()
            errmsg = "domainlist formatting error. line:{} reason:{}".format(strhostdomain,str(exc_value))

        if hostname != "" :
            fqdn = hostname + "." + domainname
        else:
            fqdn = domainname

        errmsg = update_ip(ip_new,domainname,hostname,userid,password)
        if errmsg != None :
            write_log(fqdn + ":" +errmsg,LOGLEVEL_WARN)
        else:
            flag_success = True
            write_log("{}: The IP address update was successful. ip address:{}".format(fqdn,ip_new),LOGLEVEL_INFO)

    if flag_success ==  False :
        write_log("",LOGLEVEL_ERROR)
        return False
    
    return True

def update_prechange(path_history,gip):
    errmsg=None
    # 履歴ファイルが存在するディレクトリに書き込み権限があることを確認
    if os.access(os.path.dirname(path_history),os.W_OK) == False:
        #ディレクトリパーミッションエラー
        errmsg="The directory does not exist or does not have write permission. path:" + os.path.dirname(path_history)
        return errmsg

    if os.path.exists(path_history) == True :
        if os.access(path_history,os.W_OK) == False:
            #ファイルパーミッションエラー
            errmsg="The file does not exist or does not have write permission. path:" + path_history
            return errmsg
    
    # IPアドレス\t更新時刻'%Y-%m-%d %H:%M:%S'
    ip = gip
    str_timestamp_now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    try :
        fh = open(path_history,"w",encoding='utf-8')
    except:
        (exc_type,exc_value,exc_traceback)=sys.exc_info()
        errmsg = "Faild to open file. path:{} reason:{}".format(path_history,str(exc_value))
        return errmsg
    
    try:
        fh.write('{}\t{}'.format(ip,str_timestamp_now))
        fh.close()
    except:
        (exc_type,exc_value,exc_traceback)=sys.exc_info()
        errmsg = "Faild to write file. path:{} reason:{}".format(path_history,str(exc_value))
        return errmsg
    
    return errmsg

def check_ip_dns(gip,domainlist):
    errmsg = None 
    result = True

    # カンマ区切りの文字列をリスト可
    listdomain=domainlist.split(',')
    for strhostdomain in listdomain:
        # ホスト名とドメイン名に分離
        listhostdomain=strhostdomain.split(' ')
        try:
            if len(listhostdomain) > 1:
                hostname=listhostdomain[0]
                domainname=listhostdomain[1]
            else:
                hostname = ""
                domainname = listhostdomain[0]
        except:
            (exc_type,exc_value,exc_traceback)=sys.exc_info()
            errmsg = "domainlist formatting error. line:{} reason:{}".format(strhostdomain,str(exc_value))
        
        if hostname != "" :
            fqdn = hostname + "." + domainname
        else:
            fqdn = domainname
        
        try:
            ip=socket.gethostbyname(fqdn)
            if LOG_VERBOSE == True : write_log("dns {}:{}".format(fqdn,ip),LOGLEVEL_INFO)
            if gip != ip :
                write_log("Detected that the resolved name and the current IP address are different. fqdn:{} ip address:{} current ip address:{}".format(fqdn,ip,gip),LOGLEVEL_INFO)
                result = False
        except:
            # 存在しないFQDNも例外になる
            write_log("FQDNs that cannot be resolved by name. fqdn:{}".format(fqdn),LOGLEVEL_INFO)
            result = False

    return result,errmsg


#--------------------------------------------------------------------#
# メイン処理                                                         #
#--------------------------------------------------------------------#
def main():
    gip=None
    errmsg=None
    preip=None
    dt_prechange=None
    flag_update=False

    if LOG_VERBOSE == True : write_log('Start',LOGLEVEL_INFO)
    
    # グローバルIPアドレスを取得
    (gip,errmsg)=get_globalip()
    if gip == None or gip == "" :
        # ここだけ子関数でログ出力した
        write_log("Failed to get global ip address.",LOGLEVEL_ERROR)
        return

    # 変更履歴ファイルから前回のIPアドレスと変更時刻を取得
    (preip,dt_prechange,errmsg)=get_prechange(PATH_PRECHANGE)
    if errmsg != None:
        write_log(errmsg,LOGLEVEL_ERROR)
        return

    # 前回変更時刻の指定日数後を計算
    dt_due = dt_prechange + timedelta(days=DAYS_FORCE_UPDATE)

    # 現在の時刻を取得
    dt_now = datetime.now()

    if LOG_VERBOSE == True : write_log('gip:{} pre gip:{} prechange:{} due:{} now:{}'.format(gip,preip,dt_prechange.strftime('%Y-%m-%d %H:%M:%S'),dt_due.strftime('%Y-%m-%d %H:%M:%S'),dt_now.strftime('%Y-%m-%d %H:%M:%S')),LOGLEVEL_INFO)

    # DNSチェック
    # 　DNS側も更新されていない場合、更新する
    (result,errmsg)=check_ip_dns(gip,DOMAINLIST)

    # 記録しているIPアドレスと現在のIPアドレスが異なる
    # または前回変更時刻から指定日数経過してる
    # または、DNSのIPアドレスが現在のIPアドレスが異なる場合は
    # IPアドレスを更新しに行く
    if dt_now > dt_due :
        flag_update = True
        msg="expiration date. due:{}".format(str(dt_due))
        write_log(msg,LOGLEVEL_INFO)
    if gip != preip :
        flag_update = True
        msg="Global IP address change detected. {}->{}".format(preip,gip)
        write_log(msg,LOGLEVEL_INFO)
    if flag_update == True:
        if update_ip_all(gip,DOMAINLIST,USERID,PASSWORD) == True :
            # 成功したら変更履歴ファイルを更新
            errmsg=update_prechange(PATH_PRECHANGE,gip)
            if errmsg != None:
                write_log(errmsg,LOGLEVEL_ERROR)
                return
    else:
        if LOG_VERBOSE == True : write_log('No Update',LOGLEVEL_INFO)

    if LOG_VERBOSE == True : write_log('End',LOGLEVEL_INFO)

if __name__ == "__main__":
    main()

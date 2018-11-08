# 请给点耐心往下看....你要的在后面,一条命令就OK.

## 什么是运维通道？
运维通道是联接运维人员与机器的一座桥.它跟常用的开源运维工具(`ansible`,`saltstack`,`puppet`)没有本质区别,那为什么还要重复造轮子呢?
## 运维通道有那些特点？
运维通道简单，高效，安全，可靠，可扩展．
- 简单：只有一个可执行文件，无需第三方依赖，安装(服务端，客户端)只需一条命令．客户端零配置．
- 高效: 每秒可以操纵上千台服务器．
- 安全：每个运维人员使用同的token+ip的黑白名单．
- 可靠：自动修复，过载保护
- 可扩展：可以简单配置实现集群，支持10w+客户端

## 稳定性如何？
本工具已经在线上稳定运行2年，管理机器超1Ｗ+,无出现重大问题．

## 是否开源？
涉及专利不便开源，可以在生产环境中使用．

## 硬件要求？
```
客户端千级别以下，4核8g
客户端万级别以下，8核16g
```


## 如何安装运维通道

### 安装服务端
```
mkdir -p /opt/channel
wget --no-check-certificate https://github.com/sjqzhang/ops_channel/releases/download/v1.0/CliServer  -O /opt/channel/CliServer && cd /opt/channel/ && chmod +x CliServer && ./CliServer &
```

### 安装客户端
```
wget  http://{serverip}:9160/cli/upgrade -O /bin/cli && chmod +x /bin/cli && cli daemon -s restart
```


### 简单使用(`服务端执行`)
```
cli api --token abc -u root --sudo 1 -c hostname -i ip{客户端ip}
```

## cli客户端命令

### 登陆相关
```
cli login -u username -p password #用户名密码登陆
cli logout #登出
cli register -u username -p password #注册用户 
cli enableuser -u username #启用用户
cli disableuser -u username #禁用用户
```

### shell相关
```
echo hello | cli len  ##字符串长度 数据长度等    
echo hello | cli upper  ##字符串转大写   
echo HELLO | cli lower  ##字符串转小写  
echo 'hello,world' |cli split -s ',' ##字符串分隔
echo 'hello,world' |cli split -s ','|cli join -s ' '　##数组并接  
echo 'hello,world' |cli split -s ','|cli jq -k 0 |cli join 　##数组并接 
echo 'hello,world' |cli match -m '[\w+]+$' -o aim　##字符正则匹配 -o aim (i:ignoresencase,a:all,m:mutiline) 
echo 'hello,world' |cli cut -p 5:-1  ##字符串截取
echo '{"name":"hello","date":"2018-11-09"}'|cli jq -k name  ##json解析器
cli md5 -s 'hello'　##字符md5
cli md5 -f filename ##文件md5
cli uuid ##随机uuid
cli rand ##随机数
cli randint -r 100:1000 ##100-1000随机数
cli randstr -l 20 ##随机数字符串
cli machine_id  ##客户端编号
```

### 状态相关
```
cli status
cli run_status
cli check_status
cli info
cli check -i ip(客户端ip)
cli repair -i ip(客户端ip)
```


### 文件相关
```
cli upload -f filename ##文件上传(需登陆)
cli delfile -f filename ##文件上传(需登陆)
cli listfile -d directory ##查看文件
```



### 执行命令
```
cli register -u username -p password  #注册用户
cli addtoken -t token -u user -s sudo -b blackip -w whiteip  #增加token认证
cli rshell -u username --sudo 0 --token token -i ip -d directory -f filename -a arguments -o json --async 1　-t timeout #远程执行
cli api -u username --sudo 0 --token token -c command -i ip -o json --async 1 -t timeout #执行命令
参数说明：
-i ip(在那个ip上运行指令，多个ip用英文逗号分隔)
-u username(执行的用户)
--sudo 0(0:普通用户，1:root执行)
-t timeout(超时时间,单位秒，默认：25S)
-o json/text(结果输出格式,默认：text)
--async 0(是否使用异步执行，1:异步,0:同步)
--token token(授权token)
```














package main

////#include<unistd.h>
//import "C"

import (
	"bufio"
	"bytes"
	"context"
	"crypto/md5"
	"crypto/rand"
	"crypto/tls"
	"database/sql"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"io/ioutil"
	random "math/rand"
	"net"
	"net/http"
	"net/url"
	"os"
	"os/exec"
	"os/signal"
	"os/user"
	"path/filepath"
	"reflect"
	"regexp"
	"runtime"
	"runtime/debug"
	"strconv"
	"strings"
	"syscall"
	"time"

	log "github.com/cihub/seelog"

	"github.com/astaxie/beego/httplib"
	"github.com/robfig/cron/v3"
	"github.com/sjqzhang/mahonia"

	mapset "github.com/deckarep/golang-set"
	"github.com/go-xorm/xorm"
	_ "github.com/mattn/go-sqlite3"

	"github.com/howeyc/gopass"

	"github.com/takama/daemon"

	"github.com/PuerkitoBio/goquery"
	filedriver "github.com/goftp/file-driver"
	"github.com/goftp/server"
	"github.com/syndtr/goleveldb/leveldb"

	"github.com/shirou/gopsutil/v3/cpu"
	"github.com/shirou/gopsutil/v3/disk"
	"github.com/shirou/gopsutil/v3/host"
	"github.com/shirou/gopsutil/v3/load"
	"github.com/shirou/gopsutil/v3/mem"
	psnet "github.com/shirou/gopsutil/v3/net"
)

const (
	CONST_VERSION = "2.0-20181214"

	logConfigStr = `
<seelog type="asynctimer" asyncinterval="1000" minlevel="trace" maxlevel="error">  
	<outputs formatid="common">  
		<buffered formatid="common" size="1048576" flushperiod="1000">  
			<rollingfile type="size" filename="/var/log/cli.log" maxsize="104857600" maxrolls="10"/>  
		</buffered>
	</outputs>  	  
	 <formats>
		 <format id="common" format="%Date %Time [%LEV] [%File:%Line] [%Func] %Msg%n" />  
	 </formats>  
</seelog>
`
)

var DEBUG = false
var BENCHMARK = false
var CLI_SERVER = "http://127.0.01:9160"

var PID_FILE = "/var/lib/cli/cli.pid"

var CLI_DB_FILE = "/var/lib/cli/cli.db"

var CLI_BENCHMARK = false

var HOSTNAME = ""
var util = &Common{}
var cli = NewCli()

var cronTab = newWithSeconds()
var engine *xorm.Engine

type TCron struct {
	Fid         int    `xorm:"not null pk autoincr INT(11)"`
	Fmd5        string `xorm:"not null default '' VARCHAR(64)"`
	Fip         string `xorm:"not null default '' VARCHAR(36)"`
	Fcron       string `xorm:"not null default ''  VARCHAR(128)"`
	Fjob        string `xorm:"not null default ''  VARCHAR(256)`
	Ftimeout    int    `xorm:"not null default -1 INT(11)"`
	Fdesc       string `xorm:"not null default '' VARCHAR(1024)""`
	Fstatus     int    `xorm:"not null default '-1' INT(11)""`
	Fenable     int    `xorm:"not null default '1' INT(11)""`
	Furl        string `xorm:"not null default '' VARCHAR(128)"`
	Fpid        int    `xorm:"not null default '0' int(11)"`
	FlastUpdate string `xorm:"not null default '' VARCHAR(128)"`
	Fresult     string `xorm:"not null default '' TEXT"`
}

type CliCommon struct {
	UrlSuccess string `json:"url_success"`
	Url        string `json:"url"`
	Cmd        string `json:"cmd"`
	UrlError   string `json:"url_error"`
	User       string `json:"user"`
	Timeout    string `json:"timeout"`
	Feedback   string `json:"feedback"`
	LogToFile  string `json:"log_to_file"`
	Md5        string `json:"md5"`
	SysUser    string `json:"sys_user"`
	TaskId     string `json:"task_id"`
	Extra      string `json:"extra"`
	BatchId    string `json:"batch_id"`
}

type EtcdConf struct {
	User     string   `json:"user"`
	Password string   `json:"password"`
	Server   []string `json:"server"`
	Prefix   string   `json:"prefix"`
}

type HeartBeatResult struct {
	Etcd  *EtcdConf `json:"etcd"`
	shell string    `json:"shell"`
	Salt  string    `json:"salt"`
}

type Config struct {
	EnterURL      string
	DefaultModule string
	DefaultAction string
	ScriptPath    string
	Salt          string
	Args          []string
	EtcdConf      *EtcdConf
	ShellStr      string
	Commands      chan interface{}
	Indexs        []int64
	_Args         string
	_ArgsSep      string
	UUID          string
	IP            string
}

// 用于自动上执主机信息
type CPUInfo struct {
	ModelName string `json:"model_name"`
	Cores     int    `json:"cores"`
}

type DiskInfo struct {
	MountPoint   string  `json:"mount_point"`
	TotalGB      float64 `json:"total_gb"`
	FreeGB       float64 `json:"free_gb"`
	UsagePercent float64 `json:"usage_percent"`
}

type NetworkInterface struct {
	Name string `json:"name"`
}

type SystemLoad struct {
	OneMin     float64 `json:"one_min"`
	FiveMin    float64 `json:"five_min"`
	FifteenMin float64 `json:"fifteen_min"`
}

type SystemInfo struct {
	OS             string             `json:"os"`
	Arch           string             `json:"arch"`
	CPUCores       int                `json:"cpu_cores"`
	Interfaces     []NetworkInterface `json:"network_interfaces"`
	Hostname       string             `json:"hostname"`
	MemoryTotalMB  float64            `json:"memory_total_mb"`
	MemoryFreeMB   float64            `json:"memory_free_mb"`
	MemoryUsedMB   float64            `json:"memory_used_mb"`
	MemoryUsage    float64            `json:"memory_usage"`
	CPU            []CPUInfo          `json:"cpu"`
	NetworkTraffic struct {
		BytesReceived uint64 `json:"bytes_received"`
		BytesSent     uint64 `json:"bytes_sent"`
	} `json:"network_traffic"`
	BootTime string     `json:"boot_time"`
	CPUUsage float64    `json:"cpu_usage"`
	Disks    []DiskInfo `json:"disks"`
	Load     SystemLoad `json:"load"`
}

func GetSystemInfo() SystemInfo {
	var info SystemInfo

	// 系统信息
	info.OS = runtime.GOOS
	info.Arch = runtime.GOARCH
	info.CPUCores = runtime.GOMAXPROCS(0)

	if loadInfo, err := load.Avg(); err == nil {
		info.Load = SystemLoad{
			OneMin:     loadInfo.Load1,
			FiveMin:    loadInfo.Load5,
			FifteenMin: loadInfo.Load15,
		}
	}

	// 接口信息
	if interfaces, err := psnet.Interfaces(); err == nil {
		for _, iface := range interfaces {
			info.Interfaces = append(info.Interfaces, NetworkInterface{Name: iface.Name})
		}
	}

	// 主机名
	info.Hostname, _ = os.Hostname()

	// 内存信息
	v, _ := mem.VirtualMemory()
	info.MemoryTotalMB = float64(v.Total / 1024 / 1024)
	info.MemoryFreeMB = float64(v.Available / 1024 / 1024)
	info.MemoryUsedMB = float64(v.Used / 1024 / 1024)
	info.MemoryUsage = v.UsedPercent

	// CPU信息
	if c, err := cpu.Info(); err == nil {
		for _, subCpu := range c {
			info.CPU = append(info.CPU, CPUInfo{ModelName: subCpu.ModelName, Cores: int(subCpu.Cores)})
		}
	}

	// 网络流量
	if nv, err := psnet.IOCounters(true); err == nil {
		info.NetworkTraffic.BytesReceived = nv[0].BytesRecv
		info.NetworkTraffic.BytesSent = nv[0].BytesSent
	}

	// 启动时间
	if boottime, err := host.BootTime(); err == nil {
		info.BootTime = time.Unix(int64(boottime), 0).Format("2006-01-02 15:04:05")
	}
	// CPU使用率
	if cc, err := cpu.Percent(time.Second, false); err == nil {
		if len(cc) > 0 {
			info.CPUUsage = cc[0]
		}
	}

	// 磁盘使用情况
	if parts, err := disk.Partitions(false); err == nil {
		for _, part := range parts {
			usage, _ := disk.Usage(part.Mountpoint)
			info.Disks = append(info.Disks, DiskInfo{
				MountPoint:   part.Mountpoint,
				TotalGB:      float64(usage.Total / 1024 / 1024 / 1024),
				FreeGB:       float64(usage.Free / 1024 / 1024 / 1024),
				UsagePercent: usage.UsedPercent,
			})
		}
	}
	return info

}
func Contain(obj interface{}, target interface{}) (bool, error) {
	targetValue := reflect.ValueOf(target)
	switch reflect.TypeOf(target).Kind() {
	case reflect.Slice, reflect.Array:
		for i := 0; i < targetValue.Len(); i++ {
			if targetValue.Index(i).Interface() == obj {
				return true, nil
			}
		}
	case reflect.Map:
		if targetValue.MapIndex(reflect.ValueOf(obj)).IsValid() {
			return true, nil
		}
	}

	return false, errors.New("not in array")
}

func newWithSeconds() *cron.Cron {
	secondParser := cron.NewParser(cron.Second | cron.Minute |
		cron.Hour | cron.Dom | cron.Month | cron.DowOptional | cron.Descriptor)
	return cron.New(cron.WithParser(secondParser), cron.WithChain())
}

func NewConfig() *Config {

	server := os.Getenv("CLI_SERVER")

	if server != "" {
		util.SetCliValByKey("server", server)
	} else {
		server = util.GetCliValByKey("server")
	}
	DefaultModule := "cli"
	var scriptPath = "/tmp/script/"

	if server != "" && strings.HasPrefix(server, "http") {
		if info, ok := url.Parse(server); ok == nil {
			if len(info.Path) > 1 {
				DefaultModule = info.Path[1:]
			}
			CLI_SERVER = info.Scheme + "://" + info.Host
		}

	}
	tt := strings.Split(CLI_SERVER, ":")
	if len(tt) > 3 {
		var t []string
		for i, v := range tt {
			if i != 2 {
				t = append(t, v)
			}
		}
		CLI_SERVER = strings.Join(t, ":")
	}

	if _debug := os.Getenv("CLI_DEBUG"); _debug != "" {
		DEBUG = true
	}

	if "windows" == runtime.GOOS {
		if user, err := user.Current(); err == nil {
			scriptPath = user.HomeDir + "/scirpt/"
		}
	}

	conf := &Config{
		EnterURL:      CLI_SERVER,
		DefaultModule: DefaultModule,
		Salt:          "",
		EtcdConf: &EtcdConf{
			Prefix: "",
			Server: []string{},
		},
		ScriptPath:    scriptPath,
		DefaultAction: "help",
		ShellStr:      "",
		Commands:      make(chan interface{}, 1000),
		Args:          os.Args,
		_ArgsSep:      "$$$$",
		_Args:         strings.Join(os.Args, "$$$$"),
	}

	if err := os.MkdirAll(conf.ScriptPath, 0777); err != nil {
		log.Error(err)
		os.Exit(-1)
	}

	return conf
}

type Common struct {
}

func (this *Common) GetArgsMap() map[string]string {

	return this.ParseArgs(strings.Join(os.Args, "$$$$"), "$$$$")

}

func (this *Common) Home() (string, error) {
	user, err := user.Current()
	if nil == err {
		return user.HomeDir, nil
	}

	if "windows" == runtime.GOOS {
		return this.homeWindows()
	}

	return this.homeUnix()
}

func (this *Common) SqliteExec(filename string, s string) (int64, error) {
	var (
		err    error
		db     *sql.DB
		result sql.Result
	)
	if filename == "" {
		filename = ":memory:"
	}
	if db, err = sql.Open("sqlite3", filename); err != nil {
		return -1, err
	}

	if result, err = db.Exec(s); err != nil {
		return -1, err
	}
	return result.RowsAffected()

}

func (this *Common) Color(m string, c string) string {
	color := func(m string, c string) string {
		colorMap := make(map[string]string)
		if c == "" {
			c = "green"
		}
		black := fmt.Sprintf("\033[30m%s\033[0m", m)
		red := fmt.Sprintf("\033[31m%s\033[0m", m)
		green := fmt.Sprintf("\033[32m%s\033[0m", m)
		yello := fmt.Sprintf("\033[33m%s\033[0m", m)
		blue := fmt.Sprintf("\033[34m%s\033[0m", m)
		purple := fmt.Sprintf("\033[35m%s\033[0m", m)
		white := fmt.Sprintf("\033[37m%s\033[0m", m)
		glint := fmt.Sprintf("\033[5;31m%s\033[0m", m)
		colorMap["black"] = black
		colorMap["red"] = red
		colorMap["green"] = green
		colorMap["yello"] = yello
		colorMap["yellow"] = yello
		colorMap["blue"] = blue
		colorMap["purple"] = purple
		colorMap["white"] = white
		colorMap["glint"] = glint
		if v, ok := colorMap[c]; ok {
			return v
		} else {
			return colorMap["green"]
		}
	}
	return color(m, c)
}

func (this *Common) Jq(data interface{}, key string) interface{} {
	if v, ok := data.(string); ok {
		data = this.JsonDecode(v)
	}
	if v, ok := data.([]byte); ok {
		data = this.JsonDecode(string(v))
	}
	var obj interface{}
	var ks []string
	if strings.Contains(key, ",") {
		ks = strings.Split(key, ",")
	} else {
		ks = strings.Split(key, ".")
	}
	obj = data

	ParseDict := func(obj interface{}, key string) interface{} {
		switch obj.(type) {
		case map[string]interface{}:
			if v, ok := obj.(map[string]interface{})[key]; ok {
				return v
			}
		}
		return nil

	}

	ParseList := func(obj interface{}, key string) interface{} {
		var ret []interface{}
		switch obj.(type) {
		case []interface{}:
			if ok, _ := regexp.MatchString("^\\d+$", key); ok {
				i, _ := strconv.Atoi(key)
				return obj.([]interface{})[i]
			}

			for _, v := range obj.([]interface{}) {
				switch v.(type) {
				case map[string]interface{}:
					if key == "*" {
						for _, vv := range v.(map[string]interface{}) {
							ret = append(ret, vv)
						}
					} else {
						if vv, ok := v.(map[string]interface{})[key]; ok {
							ret = append(ret, vv)
						}
					}
				case []interface{}:
					if key == "*" {
						for _, vv := range v.([]interface{}) {
							ret = append(ret, vv)
						}
					} else {
						ret = append(ret, v)
					}
				}
			}
		}
		return ret
	}
	if key != "" {
		for _, k := range ks {
			switch obj.(type) {
			case map[string]interface{}:
				obj = ParseDict(obj, k)
			case []interface{}:
				obj = ParseList(obj, k)
			}
		}
	}
	return obj
}

func (this *Common) SqliteQuery(filename string, s string) ([]map[string]interface{}, error) {
	var (
		err     error
		db      *sql.DB
		rows    *sql.Rows
		records []map[string]interface{}
	)

	if filename == "" {
		filename = ":memory:"
	}
	if db, err = sql.Open("sqlite3", filename); err != nil {
		return nil, err
	}

	rows, err = db.Query(s)

	if err != nil {
		log.Error(err)
		return nil, err
	}
	defer rows.Close()

	records = []map[string]interface{}{}
	for rows.Next() {
		record := map[string]interface{}{}

		columns, err := rows.Columns()
		if err != nil {
			log.Error(
				err, "unable to obtain rows columns",
			)
			continue
		}

		pointers := []interface{}{}
		for _, column := range columns {
			var value interface{}
			pointers = append(pointers, &value)
			record[column] = &value
		}

		err = rows.Scan(pointers...)
		if err != nil {
			log.Error(err, "can't read result records")
			continue
		}

		for key, value := range record {
			indirect := *value.(*interface{})
			if value, ok := indirect.([]byte); ok {
				record[key] = string(value)
			} else {
				record[key] = indirect
			}
		}

		records = append(records, record)
	}

	return records, nil

}

func (this *Common) SqliteInsert(filename string, table string, records []interface{}) (*sql.DB, error) {

	var (
		err error
		db  *sql.DB
	)

	if filename == "" {
		filename = ":memory:"
	}
	if db, err = sql.Open("sqlite3", filename); err != nil {
		return nil, err
	}

	Push := func(db *sql.DB, table string, records []interface{}) error {
		hashKeys := map[string]struct{}{}

		keyword := []string{"ALTER",
			"CLOSE",
			"COMMIT",
			"CREATE",
			"DECLARE",
			"DELETE",
			"DENY",
			"DESCRIBE",
			"DOMAIN",
			"DROP",
			"EXECUTE",
			"EXPLAN",
			"FETCH",
			"GRANT",
			"INDEX",
			"INSERT",
			"OPEN",
			"PREPARE",
			"PROCEDURE",
			"REVOKE",
			"ROLLBACK",
			"SCHEMA",
			"SELECT",
			"SET",
			"SQL",
			"TABLE",
			"TRANSACTION",
			"TRIGGER",
			"UPDATE",
			"VIEW",
			"GROUP"}
		_ = keyword
		for _, record := range records {
			switch record.(type) {
			case map[string]interface{}:
				for key, _ := range record.(map[string]interface{}) {
					if strings.HasPrefix(key, "`") {
						continue
					}
					key2 := fmt.Sprintf("`%s`", key)
					record.(map[string]interface{})[key2] = record.(map[string]interface{})[key]
					delete(record.(map[string]interface{}), key)
					hashKeys[key2] = struct{}{}
				}
			}
		}

		keys := []string{}

		for key, _ := range hashKeys {
			keys = append(keys, key)
		}

		//		db.Exec("DROP TABLE data")
		query := fmt.Sprintf("CREATE TABLE %s ("+strings.Join(keys, ",")+")", table)
		if _, err := db.Exec(query); err != nil {
			//fmt.Println(query)
			log.Error(err)
		}

		for _, record := range records {
			recordKeys := []string{}
			recordValues := []string{}
			recordArgs := []interface{}{}

			switch record.(type) {
			case map[string]interface{}:

				for key, value := range record.(map[string]interface{}) {
					recordKeys = append(recordKeys, key)
					recordValues = append(recordValues, "?")
					recordArgs = append(recordArgs, value)
				}

			}

			query := fmt.Sprintf("INSERT INTO %s ("+strings.Join(recordKeys, ",")+
				") VALUES ("+strings.Join(recordValues, ", ")+")", table)

			statement, err := db.Prepare(query)
			if err != nil {
				log.Error(
					err, "can't prepare query: %s", query,
				)
				continue

			}

			_, err = statement.Exec(recordArgs...)
			if err != nil {
				log.Error(
					err, "can't insert record",
				)

			}
			statement.Close()
		}

		return nil
	}

	err = Push(db, table, records)
	if err != nil {
		return nil, err
	}

	return db, err

}

func (this *Common) GBKToUTF(str string) string {
	decoder := mahonia.NewDecoder("GBK")
	if decoder != nil {
		if str, ok := decoder.ConvertStringOK(str); ok {
			return str
		}
	}
	return str
}

func (this *Common) Contains(obj interface{}, arrayobj interface{}) bool {
	targetValue := reflect.ValueOf(arrayobj)
	switch reflect.TypeOf(arrayobj).Kind() {
	case reflect.Slice, reflect.Array:
		for i := 0; i < targetValue.Len(); i++ {
			if targetValue.Index(i).Interface() == obj {
				return true
			}
		}
	case reflect.Map:
		if targetValue.MapIndex(reflect.ValueOf(obj)).IsValid() {
			return true
		}
	}
	return false
}

func (this *Common) Replace(s string, o string, n string) string {
	reg := regexp.MustCompile(o)
	s = reg.ReplaceAllString(s, n)
	return s
}
func (this *Common) homeUnix() (string, error) {
	// First prefer the HOME environmental variable
	if home := os.Getenv("HOME"); home != "" {
		return home, nil
	}

	// If that fails, try the shell
	var stdout bytes.Buffer
	cmd := exec.Command("sh", "-c", "eval echo ~$USER")
	cmd.Stdout = &stdout
	if err := cmd.Run(); err != nil {
		return "", err
	}

	result := strings.TrimSpace(stdout.String())
	if result == "" {
		return "", errors.New("blank output when reading home directory")
	}

	return result, nil
}

func (this *Common) homeWindows() (string, error) {
	drive := os.Getenv("HOMEDRIVE")
	path := os.Getenv("HOMEPATH")
	home := drive + path
	if drive == "" || path == "" {
		home = os.Getenv("USERPROFILE")
	}
	if home == "" {
		return "", errors.New("HOMEDRIVE, HOMEPATH, and USERPROFILE are blank")
	}

	return home, nil
}

func (this *Common) RandInt(min, max int) int {
	r := random.New(random.NewSource(time.Now().UnixNano()))
	if min >= max {
		return max
	}
	return r.Intn(max-min) + min
}
func (this *Common) GetAllIps() []string {
	ips := []string{}
	addrs, err := net.InterfaceAddrs()
	if err != nil {
		panic(err)
	}
	for _, addr := range addrs {
		ip := addr.String()
		pos := strings.Index(ip, "/")
		if match, _ := regexp.MatchString("(\\d+\\.){3}\\d+", ip); match {
			if pos != -1 {
				ips = append(ips, ip[0:pos])
			}
		}
	}
	return ips
}

func (this *Common) GetLocalIP() string {

	ips := this.GetAllIps()
	for _, v := range ips {
		if strings.HasPrefix(v, "10.") || strings.HasPrefix(v, "172.") || strings.HasPrefix(v, "172.") {
			return v
		}
	}
	return "127.0.0.1"

}

func (this *Common) JsonEncode(v interface{}) string {

	if v == nil {
		return ""
	}
	jbyte, err := json.Marshal(v)
	if err == nil {
		return string(jbyte)
	} else {
		return ""
	}

}

func (this *Common) JsonEncodePretty(o interface{}) string {

	resp := ""
	switch o.(type) {
	case map[string]interface{}:
		if data, err := json.Marshal(o); err == nil {
			resp = string(data)
		}
	case map[string]string:
		if data, err := json.Marshal(o); err == nil {
			resp = string(data)
		}
	case []interface{}:
		if data, err := json.Marshal(o); err == nil {
			resp = string(data)
		}
	case []string:
		if data, err := json.Marshal(o); err == nil {
			resp = string(data)
		}
	case string:
		resp = o.(string)

	default:
		if data, err := json.Marshal(o); err == nil {
			resp = string(data)
		}

	}
	var v interface{}
	if ok := json.Unmarshal([]byte(resp), &v); ok == nil {
		if buf, ok := json.MarshalIndent(v, "", "  "); ok == nil {
			resp = string(buf)
		}
	}
	return resp

}

func (this *Common) JsonDecode(jsonstr string) interface{} {

	var v interface{}
	err := json.Unmarshal([]byte(jsonstr), &v)
	if err != nil {
		return nil

	} else {
		return v
	}

}

func (this *Common) ParseArgs(args string, sep string) map[string]string {

	ret := make(map[string]string)

	var argv []string

	argv = strings.Split(args, sep)

	for i, v := range argv {
		if strings.HasPrefix(v, "-") && len(v) == 2 {
			if i+1 < len(argv) && !strings.HasPrefix(argv[i+1], "-") {
				ret[v[1:]] = argv[i+1]
			}
		}

	}
	for i, v := range argv {
		if strings.HasPrefix(v, "-") && len(v) == 2 {
			if i+1 < len(argv) && strings.HasPrefix(argv[i+1], "-") {
				ret[v[1:]] = "1"
			} else if i+1 == len(argv) {
				ret[v[1:]] = "1"
			}
		}

	}

	for i, v := range argv {
		if strings.HasPrefix(v, "--") && len(v) > 3 {
			if i+1 < len(argv) && !strings.HasPrefix(argv[i+1], "--") {
				ret[v[2:]] = argv[i+1]
			}
		}

	}
	for i, v := range argv {
		if strings.HasPrefix(v, "--") && len(v) > 3 {
			if i+1 < len(argv) && strings.HasPrefix(argv[i+1], "--") {
				ret[v[2:]] = "1"
			} else if i+1 == len(argv) {
				ret[v[2:]] = "1"
			}
		}

	}
	for k, v := range ret {
		if k == "file" && this.IsExist(v) {
			ret[k] = this.ReadFile(v)
		}
	}
	return ret

}

func (this *Common) GetModule(conf *Config) string {

	if len(os.Args) > 2 {
		if !strings.HasPrefix(os.Args[1], "-") && !strings.HasPrefix(os.Args[2], "-") {
			return os.Args[1]
		} else {
			return conf.DefaultModule
		}
	} else if len(os.Args) == 2 {
		return conf.DefaultModule
	} else {
		return conf.DefaultModule
	}

}

func (this *Common) MD5File(fn string) string {
	file, err := os.Open(fn)
	if err != nil {
		return ""
	}
	defer file.Close()
	md5 := md5.New()
	io.Copy(md5, file)
	return hex.EncodeToString(md5.Sum(nil))
}

func (this *Common) MD5(str string) string {

	md := md5.New()
	md.Write([]byte(str))
	return fmt.Sprintf("%x", md.Sum(nil))
}

func (this *Common) GetHostName() string {
	if HOSTNAME != "" && BENCHMARK {
		return HOSTNAME
	}
	result, _, _ := this.Exec([]string{"hostname"}, 5, nil)
	HOSTNAME = strings.Trim(result, "\r\n")
	return HOSTNAME
}

func (this *Common) IsExist(filename string) bool {
	_, err := os.Stat(filename)
	return err == nil || os.IsExist(err)
}

func (this *Common) ReadFile(path string) string {
	if this.IsExist(path) {
		fi, err := os.Open(path)
		if err != nil {
			return ""
		}
		defer fi.Close()
		fd, err := ioutil.ReadAll(fi)
		return string(fd)
	} else {
		return ""
	}
}

func (this *Common) WriteFile(path string, content string) bool {
	var f *os.File
	var err error
	if this.IsExist(path) {
		err = os.Remove(path)
		if err != nil {
			return false
		}
		f, err = os.Create(path)
	} else {
		f, err = os.Create(path)
	}

	if err == nil {
		defer f.Close()
		if _, err = io.WriteString(f, content); err == nil {
			//log.Debug(err)
			return true
		} else {
			return false
		}
	} else {
		//log.Warn(err)
		return false
	}

}

func (this *Common) windowsProductUUID() string {
	user, err := user.Current()
	if err != nil {
		log.Debug(err)
		return ""
	}

	filename := user.HomeDir + "/.machine_id"
	var uuid string
	if !this.IsExist(filename) {
		uuid = this.GetUUID()
		this.WriteFile(filename, uuid)
		return uuid
	}

	uuid = this.ReadFile(filename)

	if uuid == "" {
		uuid = this.GetUUID()
		this.WriteFile(filename, uuid)
		return uuid
	}

	return strings.Trim(uuid, "\n")
}

func (this *Common) IsWindows() bool {

	if "windows" == runtime.GOOS {
		return true
	}
	return false

}

func (this *Common) GetProductUUID() string {

	if "windows" == runtime.GOOS {
		uuid := this.windowsProductUUID()
		return uuid
	}

	filename := "/etc/machine_id"
	uuid := this.ReadFile(filename)
	if !this.IsExist("/etc/") {
		os.Mkdir("/etc/", 0744)
	}
	if uuid == "" {
		uuid := this.GetUUID()
		this.WriteFile(filename, uuid)
	}
	return strings.Trim(uuid, "\n ")

}

func (this *Common) Download(url string, data map[string]string) []byte {

	req := httplib.Post(url)

	for k, v := range data {
		req.Param(k, v)
	}
	str, err := req.Bytes()

	if err != nil {

		return nil

	} else {
		return str
	}
}

func (this *Common) ExecCmd(cmd []string, timeout int) string {

	var cmds []string

	if "windows" == runtime.GOOS {
		cmds = []string{
			"cmd",
			"/C",
		}
		for _, v := range cmd {
			cmds = append(cmds, v)
		}

	} else {
		cmds = []string{
			"/bin/bash",
			"-c",
		}
		for _, v := range cmd {
			cmds = append(cmds, v)
		}

	}
	result, _, _ := this.Exec(cmds, timeout, nil)
	return result
}

func (this *Common) Exec(cmd []string, timeout int, kw map[string]string) (string, string, int) {
	defer func() {
		if re := recover(); re != nil {
			buffer := debug.Stack()
			log.Error("Exec")
			log.Error(re)
			log.Error(string(buffer))
		}
	}()
	//var out bytes.Buffer

	var fp *os.File
	var ok bool
	var err error
	var taskId string
	var fpath string
	var data []byte
	var cliCommon CliCommon

	if kw != nil {
		if taskId, ok = kw["task_id"]; ok {
			kwBytes, _ := json.Marshal(kw)
			if err := json.Unmarshal(kwBytes, &cliCommon); err != nil {
				log.Error(err)
			}
		}
	}
	if taskId == "" {
		taskId = time.Now().Format("20060102150405") + fmt.Sprintf("%d", time.Now().Unix())
	}
	fpath = "/tmp/" + taskId + fmt.Sprintf("_%d", random.New(random.NewSource(time.Now().UnixNano())).Intn(60))
	fp, err = os.OpenFile(fpath, os.O_CREATE|os.O_RDWR, 0666)

	if err != nil {
		log.Error(err)
		return "", err.Error(), -1
	}
	defer fp.Close()
	duration := time.Duration(timeout) * time.Second
	if timeout == -1 {
		duration = time.Duration(60*60*24*365) * time.Second
	}
	ctx, _ := context.WithTimeout(context.Background(), duration)

	var path string

	var command *exec.Cmd
	command = exec.CommandContext(ctx, cmd[0], cmd[1:]...)
	if "windows" == runtime.GOOS {
		//		command.SysProcAttr = &syscall.SysProcAttr{HideWindow: true}

		if len(cmd) > 2 {
			cc := strings.Split(cmd[2], " ")
			if cc[0] == "powershell" {
				os.Mkdir(cli.conf.ScriptPath+"tmp", 0777)
				path = cli.conf.ScriptPath + "tmp" + "/" + this.GetUUID() + ".ps1"
				ioutil.WriteFile(path, []byte(strings.Join(cc[1:], " ")), 0777)
				command = exec.CommandContext(ctx, "powershell", []string{path}...)
			}
		}
	}
	command.Stdin = os.Stdin
	command.Stdout = fp
	command.Stderr = fp

	var flag bool
	flag = true

	CallBack2 := func(flag *bool, cliCommon *CliCommon) {
		var fp2 *os.File
		var err error
		if fp2, err = os.OpenFile(fpath, os.O_RDONLY, 0666); err != nil {
			log.Error(err)
			return
		}
		defer fp2.Close()
		r := bufio.NewReader(fp2)
		uuid := this.GetProductUUID()
		ip := this.GetLocalIP()

		Feeback := func(result string) {
			jsonData := map[string]string{
				"return_code": fmt.Sprintf("%d", -2),
				"result":      result,
				"error":       "",
				"success":     result,
				"s":           this.GetHostName(),
				"i":           ip,
				"ip":          uuid,
				"machine_id":  uuid,
				"cmd":         cliCommon.Cmd,
				"task_id":     cliCommon.TaskId,
				"batch_id":    cliCommon.BatchId,
				"extra":       cliCommon.Extra,
			}
			req := httplib.Post(cli.conf.EnterURL + "/" + cli.conf.DefaultModule + "/feedback_result2")
			for k, v := range jsonData {
				req.Param(k, v)
			}
			log.Info(req.String())
		}
		decoder := mahonia.NewDecoder("GBK")
		var lines []string
		for {
			if !*flag {
				break
			}
			by, err := r.ReadBytes('\n')
			if err != nil && err != io.EOF {
				break
			}
			if string(by) != "" {
				if this.IsWindows() && decoder != nil {
					if str, ok := decoder.ConvertStringOK(string(by)); ok {
						lines = append(lines, str)
					} else {
						lines = append(lines, string(by))
					}
				} else {
					lines = append(lines, string(by))
				}
			}
			if err == io.EOF {
				if len(lines) > 0 {
					Feeback(strings.Join(lines, ""))
				}
				lines = make([]string, 0)
				time.Sleep(time.Second)
			}

		}
	}

	_ = CallBack2

	if cliCommon.TaskId != "" {
		go CallBack2(&flag, &cliCommon)
	}

	RemoveFile := func() {
		flag = false
		fp.Close()
		if path != "" {
			os.Remove(path)
		}
		if fpath != "" {
			os.Remove(fpath)
		}
	}
	_ = RemoveFile
	defer RemoveFile()
	err = command.Run()
	if err != nil {
		if len(kw) > 0 {
			log.Info(kw)
			log.Error("error:"+err.Error(), "\ttask_id:"+fpath, "\tcmd:"+cliCommon.Cmd, "\tcmd:"+strings.Join(cmd, " "))
		} else {
			log.Info("task_id:"+fpath, "\tcmd:"+cliCommon.Cmd, "\tcmd:"+strings.Join(cmd, " "))
		}
		log.Flush()
		fp.Sync()
		//fp.Seek(0, 2)
		data, err = ioutil.ReadFile(fpath)
		if err != nil {
			log.Error(err)
			log.Flush()
			return string(data), err.Error(), -1
		}
		return string(data), "", -1
	}
	status := -1
	sysTemp := command.ProcessState
	if sysTemp != nil {
		status = sysTemp.Sys().(syscall.WaitStatus).ExitStatus()
	}
	//fp.Seek(0, 2)
	fp.Sync()
	data, err = ioutil.ReadFile(fpath)
	if this.IsWindows() {
		decoder := mahonia.NewDecoder("GBK")
		if decoder != nil {
			if str, ok := decoder.ConvertStringOK(string(data)); ok {
				return str, "", status
			}
		}
	}
	if err != nil {
		log.Error(err, cmd)
		return string(data), err.Error(), -1
	}

	return string(data), "", status
}

func (this *Common) GetUUID() string {

	b := make([]byte, 48)
	if _, err := io.ReadFull(rand.Reader, b); err != nil {
		return ""
	}
	id := this.MD5(base64.URLEncoding.EncodeToString(b))
	return fmt.Sprintf("%s-%s-%s-%s-%s", id[0:8], id[8:12], id[12:16], id[16:20], id[20:])

}

func (this *Common) GetAction(conf *Config) string {

	if len(os.Args) >= 3 {
		if !strings.HasPrefix(os.Args[2], "-") {
			return os.Args[2]
		} else if !strings.HasPrefix(os.Args[1], "-") {
			return os.Args[1]
		} else {
			return conf.DefaultAction
		}
	} else if len(os.Args) == 2 && !strings.HasPrefix(os.Args[1], "-") {
		return os.Args[1]
	} else {
		return conf.DefaultAction
	}

}

func (this *Common) GetToken() string {

	return this.GetCliValByKey("token")
}

func (this *Common) GetAuthUUID() string {
	return this.GetCliValByKey("auth-uuid")
}
func (this *Common) GetReqToken() string {
	return this.GetCliValByKey("token")
}

func (this *Common) SetCliValByKey(key string, value string) {

	keys := []string{"token", "auth-uuid", "server"}
	dict := map[string]string{}
	for _, v := range keys {
		dict[v] = ""
	}
	info, err := url.Parse(CLI_SERVER)
	if err == nil {
		if strings.Split(info.Host, ":")[0] != "127.0.0.1" {
			dict["server"] = CLI_SERVER
		}
		filename := "/var/lib/cli/.cli"
		os.MkdirAll("/var/lib/cli", 0777)
		this.WriteFile(filename, fmt.Sprintf("server=%s", CLI_SERVER))
		os.Chmod(filename, 0777)
	}
	filename := ""
	//dir := "/etc"
	dir, ok := this.Home()
	if ok != nil {
		dir = "/etc"
	}
	if this.IsExist(dir) {
		os.MkdirAll(dir, 0777)
	}
	filename = dir + "/" + ".cli"
	content := this.ReadFile(filename)
	if content != "" {
		strs := strings.Split(content, "\n")
		for _, s := range strs {
			kv := strings.Split(strings.Trim(s, " "), "=")
			if len(kv) == 2 {
				dict[kv[0]] = kv[1]
			}
		}
	}
	//	}
	dict[key] = value
	if filename != "" {
		var items []string
		for k, v := range dict {
			items = append(items, k+"="+v)
		}
		this.WriteFile(filename, strings.Join(items, "\n"))

	}

	os.Chmod(filename, 0777)

}

func (this *Common) GetCliValByKey(key string) string {
	dict := map[string]string{}
	if dir, ok := this.Home(); ok == nil {
		filename := dir + "/" + ".cli"
		if key == "server" {
			filename = "/var/lib/cli/.cli"
		}
		content := this.ReadFile(filename)
		if content != "" {
			strs := strings.Split(content, "\n")
			for _, s := range strs {
				kv := strings.Split(strings.Trim(s, " "), "=")
				if len(kv) == 2 {
					dict[kv[0]] = kv[1]
				}
			}
		}
	}
	if val, ok := dict[key]; ok {
		return val
	} else {
		return ""
	}
}

func (this *Common) Request(url string, data map[string]string) string {
	body := "{}"

	for _, k := range []string{"i", "s"} {
		if _, ok := data[k]; !ok {
			switch k {
			case "i":
				data[k] = this.GetLocalIP()
			case "s":
				data[k], _ = os.Hostname()
			}
		}

	}
	if pdata, err := json.Marshal(data); err == nil {
		body = string(pdata)
	}

	//begin
	if strings.Contains(url, "feedback_result") { // just for feedback_result,this is bad code
		data2 := make(map[string]interface{})
		for k, v := range data {
			data2[k] = v
		}
		if m, ok := data["kw"]; ok {
			var kw map[string]interface{}
			if err := json.Unmarshal([]byte(m), &kw); err == nil {
				data2["kw"] = kw
			}
		}
		if pdata, err := json.Marshal(data2); err == nil {
			body = string(pdata)
		}
	} //end

	req := httplib.Post(url)

	uuid := this.GetAuthUUID()
	token := this.GetReqToken()
	req.Header("auth-uuid", uuid)
	req.Header("token", token)
	req.Header("machine-id", this.GetProductUUID())

	req.Param("param", body)
	req.SetTimeout(time.Second*10, time.Second*60)
	str, err := req.String()
	if err != nil {
		log.Error(err, url, data)
	}
	return str
}

type Cli struct {
	util    *Common
	conf    *Config
	_daemon *Daemon
}

func NewCli() *Cli {

	var (
		cli *Cli
	)

	setting := httplib.BeegoHTTPSettings{
		UserAgent:        "beegoServer",
		ConnectTimeout:   60 * time.Second,
		ReadWriteTimeout: 60 * time.Second,
		Gzip:             true,
		DumpBody:         true,
		TLSClientConfig:  &tls.Config{InsecureSkipVerify: true},
	}

	httplib.SetDefaultSetting(setting)

	cli = &Cli{util: util, conf: NewConfig()}

	return cli

}

func (this *Cli) Help(module string, action string) {
	data := this.util.GetArgsMap()
	resp := this._Request(this.conf.EnterURL+"/"+module+"/"+action, data)
	if resp == "" {
		resp = `
        ########  登陆相关  ########
        cli login -u username -p password #用户名密码登陆
        cli logout #登出
        cli register -u username -p password #注册用户 
        cli enableuser -u username #启用用户
        cli disableuser -u username #禁用用户

        ########  shell相关  ########
        echo hello | cli len  ##字符串长度 数据长度等    
        echo hello | cli upper  ##字符串转大写   
        echo HELLO | cli lower  ##字符串转小写  
        echo 'hello,world' |cli split -s ',' ##字符串分隔
        echo 'hello,world' |cli split -s ','|cli join -s ' '　##数组并接  
        echo 'hello,world' |cli split -s ','|cli jq -k 0 |cli join 　##数组并接 
        echo 'hello,world' |cli match -m '[\w+]+$' -o aim　##字符正则匹配 -o aim (i:ignoresencase,a:all,m:mutiline) 
        echo 'hello,world' |cli cut -p 5:-1  ##字符串截取
        echo '{"name":"hello","date":"2018-11-09"}'|cli jq -k name  ##json解析器
        echo '[{"name":"hello","date":"2018-11-09"}]'|cli jf -w "name='hello'" -c name  ##json 过滤器
        cli md5 -s 'hello'　##字符md5
        cli color -m 'hello' -c green　##有色输出 c(green|red|blue|yello|glint|white|black)
        cli jq -k key ## json解析器，-k json中的key，嵌套时使用逗号分隔，如 -k data,rows,ip  
        cli jf -w where -c column ## json 数组过滤器  -w sql中的where条件 如 -w "name='jqzhang' and group='devops' " -c sql中的column 用逗号分隔 如 -c name,group  
        cli md5 -f filename ##文件md5
        cli kv -k key -v value ## 本地KV临时存储只支持json 也支持管道，例如： echo '{"name":"jqzhang"}' | o kv -k name -v
        cli uuid ##随机uuid
        cli rand ##随机数
        cli randint -r 100:1000 ##100-1000随机数
        cli randstr -l 20 ##随机数字符串
        cli machine_id  ##客户端编号

        ########  状态相关  ########
        cli status
        cli run_status
        cli check_status
        cli info
        cli check -i ip(客户端ip)
        cli repair -i ip(客户端ip)
        cli unrepair -a (add|del) -i ip ##增加或删除不需要自动修复列表


        ########  文件相关  ########
        cli upload -f filename ##文件上传(需登陆)
        cli scp -f filename -u user -d destination(remote) -i ip  ##复制文件到远程机器(需有token)
        cli delfile -f filename ##文件上传(需登陆)
        cli listfile -d directory ##查看文件


        ########  (命令/脚本)执行  ########
        cli cmd -u user --sudo 1 -c cmd -i ip -t timeout ## sudo 是否(1:是,0:否)
        cli rshell -f filename -d username -a argument(json) -t timeout ##远程执行脚本,脚本要先上传

		`
	}
	filename := os.Args[0]
	if strings.HasSuffix(filename, "o") {
		resp = strings.Replace(resp, "cli ", "o ", -1)
	}
	fmt.Println(resp)
}

func (this *Cli) Default(module string, action string) {
	data := this.util.GetArgsMap()
	resp := this._Request(this.conf.EnterURL+"/"+module+"/"+action, data)

	var v interface{}
	if ok := json.Unmarshal([]byte(resp), &v); ok == nil {
		if buf, ok := json.MarshalIndent(v, "", "  "); ok == nil {
			resp = string(buf)
		}
	}

	fmt.Println(resp)
}

func (this *Cli) _Default(module string, action string, data map[string]string) {

	resp := this._Request(this.conf.EnterURL+"/"+module+"/"+action, data)
	fmt.Println(resp)
}

func (this *Cli) _Request(url string, data map[string]string) string {
	resp := this.util.Request(url, data)
	return resp
}

func (this *Cli) Kv(module string, action string) {
	var (
		home     string
		body     map[string]string
		filename string
		err      error
		db       *leveldb.DB
		k        string
		v        string
		data     []byte
		obj      interface{}
	)

	body = this.util.GetArgsMap()

	if _v, ok := body["k"]; ok {
		k = _v
	} else {
		fmt.Println("(error) -k(key) require")
		return
	}

	if _v, ok := body["v"]; ok {
		v = _v
		if v == "1" || v == "" {
			obj, v = this.StdinJson(module, action)
		}

		if err = json.Unmarshal([]byte(v), &obj); err != nil {
			log.Error(err)
			return
		}
	}

	if home, err = this.util.Home(); err != nil {
		home = "./"
	}
	filename = home + "/" + "o.db"

	db, err = leveldb.OpenFile(filename, nil)
	if err != nil {
		log.Error(err)
		return
	}

	if v == "" {
		data, err = db.Get([]byte(k), nil)
		if err != nil {
			log.Error(err)
			return
		}
		fmt.Println(string(data))
	} else {
		err = db.Put([]byte(k), []byte(v), nil)
		if err != nil {
			log.Error(err)
			return
		}
		fmt.Println("ok")

	}

}

func (this *Cli) Request(module string, action string) {
	var (
		err  error
		ok   bool
		body map[string]string
		v    string
		k    string
		u    string
		req  *httplib.BeegoHTTPRequest
		html string
	)
	data := this.util.GetArgsMap()
	_ = data

	if v, ok = data["u"]; ok {
		u = v
	}

	if v, ok = data["url"]; ok {
		u = v
	}

	if u == "" {
		fmt.Println("(error) -u(url) require")
		return
	}

	if v, ok = data["d"]; ok {
		if err = json.Unmarshal([]byte(v), &body); err != nil {
			fmt.Println(err)
			return
		}
		req = httplib.Post(u)
		for k, v = range body {

			req.Param(k, v)

		}

		if v, ok = data["f"]; ok {

			if this.util.IsExist(v) {
				req.PostFile("file", v)
			}

		}

		if html, err = req.String(); err != nil {
			log.Error(err)
			fmt.Println(err)
			return
		}
		fmt.Println(this.util.GBKToUTF(html))
		return
	} else {
		req = httplib.Get(u)
		if html, err = req.String(); err != nil {
			log.Error(err)
			fmt.Println(err)
			return
		}
		fmt.Println(this.util.GBKToUTF(html))
		return
	}

}

func (this *Cli) Heartbeat(uuid string) {

	defer func() {
		if re := recover(); re != nil {
			buffer := debug.Stack()
			log.Error("Heartbeat")
			log.Error(re)
			log.Error(string(buffer))
			log.Flush()
		}
	}()

	for {
		if uuid == "" {
			uuid = this.util.GetProductUUID()
		}
		var cmds []string
		if "windows" == runtime.GOOS {
			cmds = []string{
				"cmd",
				"/c",
				this.conf.ShellStr,
			}
		} else {
			cmds = []string{
				"/bin/bash",
				"-c",
				this.conf.ShellStr,
			}
		}
		var data map[string]string
		//将环境变量转化为map的形式存储到变量envs中
		envs := make(map[string]string)

		// 遍历环境变量
		for _, env := range os.Environ() {
			// 使用=分割环境变量，得到key和value
			pair := strings.SplitN(env, "=", 2)
			if len(pair) == 2 {
				// 将key和value存入map中
				envs[pair[0]] = pair[1]
			}
		}

		// 打印环境变量map，以验证结果
		//for key, value := range envs {
		//	fmt.Println(key, ":", value)
		//}
		env, err := json.MarshalIndent(envs, "", " ")
		envstr := "{}"
		if err == nil {
			envstr = string(env)
		}
		systemInfo := GetSystemInfo()
		systemInfoStr := "{}"
		if v, err := json.MarshalIndent(systemInfo, "", " "); err == nil {
			systemInfoStr = string(v)
		}
		if this.conf.ShellStr == "" {
			data = map[string]string{
				"ips":         strings.Join(this.util.GetAllIps(), ","),
				"uuid":        uuid,
				"status":      "online",
				"envs":        envstr,
				"system_info": systemInfoStr,
				"utime":       time.Now().Format("2006-01-02 15:04:05"),
				"platform":    strings.ToLower(runtime.GOOS),
				"hostname":    this.util.GetHostName(),
			}
		} else {
			statusstr, _, _ := this.util.Exec(cmds, 60*5, nil)
			data = map[string]string{
				"ips":         strings.Join(this.util.GetAllIps(), ","),
				"uuid":        uuid,
				"status":      statusstr,
				"envs":        envstr,
				"system_info": systemInfoStr,
				"utime":       time.Now().Format("2006-01-02 15:04:05"),
				"platform":    strings.ToLower(runtime.GOOS),
				"hostname":    this.util.GetHostName(),
			}
		}

		url := this.conf.EnterURL + "/" + this.conf.DefaultModule + "/" + "heartbeat"

		heartbeats := this._Request(url, data)

		if DEBUG {

			log.Debug(heartbeats)

		}

		//		var js map[string]interface{}
		var js HeartBeatResult
		ok := json.Unmarshal([]byte(heartbeats), &js)
		//		fmt.Println("heartbeat", heartbeats)
		//		fmt.Println("heartbeat", js)
		if ok == nil {
			this.conf.Salt = js.Salt
			this.conf.ShellStr = js.shell
			this.conf.EtcdConf = js.Etcd
			log.Info(fmt.Sprintf("heartbeat2server %s ok", this.conf.EnterURL))

		} else {
			log.Info("heartbeat2server error")
		}
		r := random.New(random.NewSource(time.Now().UnixNano()))
		interval := time.Duration(60 + r.Intn(60))

		time.Sleep(interval * time.Second)
	}

}

func (this *Cli) Heartbeat2Etcd() {

	defer func() {
		if re := recover(); re != nil {
			buffer := debug.Stack()
			log.Error("Heartbeat2Etcd")
			log.Error(re)
			log.Error(string(buffer))
			log.Flush()
		}
	}()

	for {

		// server := ""
		// prefix := ""
		if len(this.conf.EtcdConf.Server) > 0 && this.conf.EtcdConf.Prefix != "" {
			// server = this.conf.EtcdConf.Server[0]
			// prefix = this.conf.EtcdConf.Prefix
			// uuid := this.util.GetProductUUID()
			// ips := this.util.GetAllIps()
			// heartbeat_url := "http://" + server + "/v2/keys" + prefix + "/heartbeat/" + uuid
			// req := httplib.Put(heartbeat_url)
			// req.SetTimeout(time.Second*30, time.Second*30)
			// req.Param("ttl", "300")
			// req.Param("value", strings.Join(ips, ","))
			// req.String()

		} else {
			log.Error("Error Etcd Config")
			print("Error Etcd Config")
		}

		r := random.New(random.NewSource(time.Now().UnixNano()))
		interval := time.Duration(60 + r.Intn(60))
		time.Sleep(interval * time.Second)

	}

}

func (this *Cli) deleteCmd(key string) {
	url := this.conf.EnterURL + "/" + this.conf.DefaultModule + "/del_etcd_key"
	request := httplib.Post(url)
	request.Param("host", this.conf.EtcdConf.Server[0])
	request.Param("key", key)
	result, err := request.SetTimeout(5*time.Second, 8*time.Second).String()
	if err != nil {
		fmt.Println("delcmd error", err)
		log.Error(err, result)
	}
	//log.Debug("delcmd", result)
}

func (this *Cli) DealCommands(uuid string) {

	defer func() {
		if re := recover(); re != nil {
			buffer := debug.Stack()
			log.Error("DealCommands")
			log.Error(re)
			log.Error(string(buffer))
			log.Flush()
		}
	}()

	if uuid == "" {
		uuid = this.util.GetProductUUID()
	}

	for {

		select {
		case item := <-this.conf.Commands:
			nodes, ok := item.(Nodes)
			if !ok {
				continue
			}

			cmd := nodes.Value

			this.deleteCmd(nodes.Key)

			var cliCommon CliCommon
			if err := json.Unmarshal([]byte(cmd), &cliCommon); err != nil {
				log.Debug(err)
				continue
			}

			md5 := this.util.MD5(cliCommon.Cmd + this.conf.Salt)
			timeout := 25
			if t, err := strconv.Atoi(cliCommon.Timeout); err == nil && t > 0 {
				timeout = t
			}
			if md5 == cliCommon.Md5 || BENCHMARK {
				os := strings.ToLower(runtime.GOOS)
				var cmds []string
				switch os {
				case "linux":
					cmds = []string{
						"/bin/bash",
						"-c",
						cliCommon.Cmd,
					}

				case "windows":
					cmds = []string{
						"cmd",
						"/c",
						cliCommon.Cmd,
					}
				default:
					cmds = []string{
						"/bin/bash",
						"-c",
						cliCommon.Cmd,
					}

				}

				if len(cmds) == 0 {
					log.Debug("cmds is null, os:", os)
					continue
				}

				CallBack := func() {

					result := ""
					fail := ""
					status := -1
					var kwBytes []byte
					kw := make(map[string]string)
					var err error

					if BENCHMARK {
						result = "ok"
						status = 0
					} else {
						kw = make(map[string]string)
						kwBytes, err = json.Marshal(cliCommon)
						if err != nil {
							log.Error(err)
						}
						json.Unmarshal(kwBytes, &kw)
						result, fail, status = this.util.Exec(cmds, timeout, kw)

					}
					jsonData := map[string]string{
						"return_code": fmt.Sprintf("%d", status),
						"result":      strings.Trim(result, "\n \t\r"),
						"error":       fail,
						"success":     strings.Trim(result, "\n \t\r"),
						"s":           this.util.GetHostName(),
						"i":           this.conf.IP,
						"ip":          uuid,
						"machine_id":  uuid,
						"cmd":         cliCommon.Cmd,
						"task_id":     cliCommon.TaskId,
						"batch_id":    cliCommon.BatchId,
						"extra":       cliCommon.Extra,
						"kw":          string(kwBytes),
					}

					log_to_file := cliCommon.LogToFile
					feedback := cliCommon.Feedback

					if log_to_file == "" {
						log_to_file = "1"
					}

					if feedback == "" {
						feedback = "1"
					}

					feedbackUrl := this.conf.EnterURL + "/" + this.conf.DefaultModule + "/feedback_result"
					log.Info("task_id:" + cliCommon.TaskId + "\tcmd:" + cliCommon.Cmd)

					if feedback == "1" {
						res := this._Request(feedbackUrl, jsonData)
						log.Info("feedback_result:", res, "\tdata:", this.util.JsonEncode(jsonData))
					}

					if log_to_file == "1" {

						log.Info("Result Success:\n", result)
						//log.Info("Result Error\t", fail)

					}

					callback := func(url string, data map[string]string) {
						request := httplib.Post(url).
							SetTimeout(5*time.Second, 5*time.Second)
						for k, v := range data {
							request.Param(k, v)
						}
						taskid, _ := data["task_id"]
						log.Info(fmt.Sprintf("task_id:%s feedback to url:%s", taskid, url))
						if s, err := request.String(); err != nil {
							log.Error(err, s)
						} else {
							log.Info("callback_result:" + s)
						}
					}
					if cliCommon.UrlSuccess != "" && status == 0 {
						callback(cliCommon.UrlSuccess, jsonData)
					}
					if cliCommon.Url != "" {
						callback(cliCommon.Url, jsonData)

					}
					if cliCommon.UrlError != "" && status != 0 {
						callback(cliCommon.UrlError, jsonData)
					}
				}

				CallBack()

			} else {
				log.Debug("sign error", nodes)
			}
		}
	}

}

type Nodes struct {
	Key           string `json:"key"`
	Value         string `json:"Value"`
	ModifiedIndex int64  `json:"modifiedIndex"`
	CreatedIndex  int64  `json:"createdIndex"`
}

type Node struct {
	Key   string  `json:"key"`
	Dir   bool    `json:"dir"`
	Nodes []Nodes `json:"nodes"`
}

type WatchData struct {
	Action string `json:"action"`
	Node   Node   `json:"node"`
}

func (this *Cli) WatchEtcd(uuid string) {

	if uuid == "" {
		uuid = this.util.GetProductUUID()
	}

	GetNodeURL := func() string {
		server := ""
		prefix := ""
		if len(this.conf.EtcdConf.Server) > 0 && this.conf.EtcdConf.Prefix != "" {
			server = this.conf.EtcdConf.Server[0]
			prefix = this.conf.EtcdConf.Prefix
			uuid = uuid
			url := server + prefix + "/servers/" + uuid
			return url
		}
		return ""
	}

	DealWithData := func(result string) {
		time.Sleep(time.Millisecond * time.Duration(this.util.RandInt(100, 300)))
		url := GetNodeURL()
		if url != "" {
			url = url + "?recursive=true"

			req := httplib.Get(url)
			req.SetBasicAuth(this.conf.EtcdConf.User, this.conf.EtcdConf.Password)

			var err error
			if result == "" {
				result, err = req.String()
			}
			//			log.Debug("WatchEtcd,URL:", url, "DealWithData result:", result)
			if err == nil {
				var watchData WatchData
				if err = json.Unmarshal([]byte(result), &watchData); err != nil {
					log.Error(err)
					return
				}
				if watchData.Action == "delete" {
					return
				}
				for _, k := range watchData.Node.Nodes {
					if DEBUG {
						log.Debug(k)

					}

					b, _ := Contain(k.CreatedIndex, this.conf.Indexs)
					if !b {

						if len(this.conf.Indexs) < 1000 {

							this.conf.Indexs = append(this.conf.Indexs, k.CreatedIndex)
						} else {
							this.conf.Indexs = this.conf.Indexs[500:]
							this.conf.Indexs = append(this.conf.Indexs, k.CreatedIndex)
						}

						this.conf.Commands <- k
					}
				}
			} else {
				time.Sleep(time.Millisecond * 500)
			}
		} else {
			time.Sleep(time.Millisecond * 500)
		}
	}

	go func() {

		for {
			DealWithData("")
			time.Sleep(time.Second * 5)
		}

	}()

	for {
		url := GetNodeURL()
		if url != "" {
			url = url + "?wait=true&recursive=true"
			if DEBUG {
				log.Debug("watch url", url)
				//				fmt.Println("watch url", url)
			}
			req := httplib.Get(url)
			req.SetBasicAuth(this.conf.EtcdConf.User, this.conf.EtcdConf.Password)
			req.SetTimeout(time.Second*5, time.Second*time.Duration(20+this.util.RandInt(1, 10)))
			data, ok := req.String()
			_ = data
			if ok == nil {
				go DealWithData("")
			} else {
				time.Sleep(time.Millisecond * 500)
			}
		} else {
			if DEBUG {
				log.Warn("can't not get url")
			}
			time.Sleep(time.Second * 3)
		}
	}
}

func (this *Cli) killPython() {
	this.util.ExecCmd([]string{"ps aux|grep python|grep 'cli daemon'|awk '{print $2}'|xargs -n 1 kill"}, 10)
}

func (this *Cli) getPids() []string {
	//cmd := `source /etc/profile ; ps aux|grep -w 'daemon -s daemon'|grep -v grep|awk '{print $2}'`
	//cmds := []string{
	//	"/bin/bash",
	//	"-c",
	//	cmd,
	//}
	//pid, _, _ := this.util.Exec(cmds, 10, nil)
	//log.Error(cmds)
	//return strings.Trim(pid, "\n ")
	pid := this.util.ReadFile(PID_FILE)
	return strings.Split(strings.TrimSpace(pid), "\n")
}
func (this *Cli) isRunning() bool {
	pids := this.getPids()
	count := 0
	for _, pid := range pids {
		if pid == "" {
			continue
		}
		if this.util.IsWindows() {
			pids := this.util.ExecCmd([]string{"tasklist", "/FI", fmt.Sprintf("PID eq %s", pid)}, 10)
			if strings.Index(pids, pid) > 0 {
				count = count + 1
			}
		} else {
			if this.util.IsExist(fmt.Sprintf("/proc/%s", pid)) {
				count = count + 1
			}
		}
	}
	if count > 1 {
		log.Error("muti process is running", pids)
		log.Flush()
		os.Exit(0)
	}
	if count == 1 {
		return true
	}
	return false
}

func (this *Cli) stop() {
	pids := this.getPids()
	for _, pid := range pids {
		if pid == "" {
			continue
		}
		if this.util.IsWindows() {
			this.util.ExecCmd([]string{"taskkill.exe", "/F", "/PID", pid}, 10)
		} else {
			//this.util.ExecCmd(strings.Split(fmt.Sprintf("sudo kill -9 %s", pid)," "), 10)
			this.util.ExecCmd([]string{fmt.Sprintf("sudo kill -9 %s", pid)}, 10)
		}
		os.Remove(PID_FILE)
	}
}

func (this *Cli) Daemon(module string, action string) {

	if len(os.Args) == 4 && (os.Args[3] == "daemon") {
		go initCron()
		cli.Run()
		return
	}
	if len(os.Args) == 4 && (os.Args[3] == "stop") {
		this.stop()
	}
	if len(os.Args) == 4 && (os.Args[3] == "status") {
		if !this.isRunning() {
			os.Remove(PID_FILE)
			fmt.Println("cli is not running")
		} else {
			fmt.Println(fmt.Sprintf("pid:%v", this.getPids()))
			fmt.Println("cli is running")
		}
		return
	}
	if len(os.Args) == 4 && (os.Args[3] == "restart" || os.Args[3] == "start") {
		//pid1 := this.getPid()
		//this.stop()
		//pid2 := this.getPid()
		//if pid2 != "" && pid1 == pid2 {
		//	fmt.Println("(error) Permission denied")
		//	return
		//}
		this.stop()
		os.Args[3] = "daemon"
		args := os.Args[1:]
		cmd := exec.Command(os.Args[0], args...)
		go func() {
			cmd.Start()
			cmd.Wait()
		}()

		time.Sleep(time.Millisecond * 300)
		return
	}

	//if msg, err := this._daemon.Manage(this); msg != "" {
	//	fmt.Println(msg, err)
	//
	//}

	//	killcmd := fmt.Sprintf("ps aux|grep 'cli daemon -s '|grep -v -E 'grep|%d'|awk '{print $2}'|xargs -n 1 kill -9 ", os.Getpid())

	//	cmd := strings.Join(os.Args, " ")

	//	reg, _ := regexp.Compile("daemon -s (start|restart)")

	//	if strings.TrimSpace(reg.FindString(cmd)) != "" {
	//		cmds := []string{
	//			"/bin/bash",
	//			"-c",
	//			killcmd,
	//		}
	//		this.util.Exec(cmds, 5)
	//		//		_ = C.daemon
	//		//		go this.Run()
	//		//		C.daemon(1, 1)
	//		this.Run()

	//	}

	//this.Run()

}

func (this *Cli) Machine_id(module string, action string) {
	uuid := this.util.GetProductUUID()
	fmt.Println(uuid)
}

func (this *Cli) Login(module string, action string) {

	user, password := this._UserInfo()

	data := map[string]string{
		"u": user,
		"p": password,
	}

	res := this._Request(this.conf.EnterURL+"/"+this.conf.DefaultModule+"/login", data)

	if _, ok := this.util.Home(); ok == nil {

		if len(res) == 36 {
			this.util.SetCliValByKey("auth-uuid", res)
			fmt.Println("success")

		} else {

			fmt.Println(res)
		}

	}

	//	print(res)
}

func (this *Cli) _UserInfo() (string, string) {
	argv := this.util.GetArgsMap()
	var password string
	var user string
	if _user, ok := argv["u"]; ok {
		user = _user
	} else {
		fmt.Println("please input username:")
		fmt.Scanln(&user)
	}
	if _password, ok := argv["p"]; ok {
		password = _password
	} else {
		fmt.Println("please input password:")
		_password, er := gopass.GetPasswd()
		if er != nil {
		} else {
			password = string(_password)
		}
	}
	return user, password
}

func (this *Cli) Logout(module string, action string) {

	print(module)
	print(action)

}

func (this *Cli) Register(module string, action string) {

	user, password := this._UserInfo()
	data := map[string]string{
		"u": user,
		"p": password,
	}
	this._Default(module, action, data)

}

func (this *Cli) Shell(module string, action string) {
	var err error
	var includeReg *regexp.Regexp
	src := ""
	argv := this.util.GetArgsMap()
	file := ""
	dir := ""
	update := "0"
	debug := "0"
	timeout := -1
	ok := true
	if v, ok := argv["u"]; ok {
		update = v
	}

	if v, ok := argv["x"]; ok {
		debug = v
	}

	if v, ok := argv["t"]; ok {
		timeout, _ = strconv.Atoi(v)
	}

	if file, ok = argv["f"]; !ok {
		fmt.Println("-f(filename) is required")
		return
	}

	if dir, ok = argv["d"]; !ok {
		dir = "shell"
	}

	path := this.conf.ScriptPath + dir
	if !this.util.IsExist(path) {
		log.Debug(os.MkdirAll(path, 0777))
	}
	os.Chmod(path, 0777)

	includeRegStr := `#include\s+-f\s+(?P<filename>[a-zA-Z.0-9_-]+)?\s+-d\s+(?P<dir>[a-zA-Z.0-9_-]+)?|#include\s+-d\s+(?P<dir2>[a-zA-Z.0-9_-]+)?\s+-f\s+(?P<filename2>[a-zA-Z.0-9_-]+)?`
	DownloadShell := func(dir, file string) (string, error) {
		req := httplib.Post(this.conf.EnterURL + "/" + this.conf.DefaultModule + "/shell")
		req.Param("dir", dir)
		req.Param("file", file)
		return req.String()
	}

	DownloadIncludue := func(includeStr string) string {
		type DF struct {
			Dir  string
			File string
		}
		df := DF{}
		parts := strings.Split(includeStr, " ")
		for i, v := range parts {
			if v == "-d" {
				df.Dir = parts[i+1]
			}
			if v == "-f" {
				df.File = parts[i+1]
			}
		}

		if s, err := DownloadShell(df.Dir, df.File); err != nil {
			log.Error(err)
			return includeStr
		} else {
			return s
		}

	}
	fpath := path + "/" + file
	fpath = strings.Replace(fpath, "///", "/", -1)
	fpath = strings.Replace(fpath, "//", "/", -1)

	if update == "1" || !this.util.IsExist(fpath) {
		if src, err = DownloadShell(dir, file); err != nil {
			log.Error(err)
			return
		}

		if includeReg, err = regexp.Compile(includeRegStr); err != nil {
			log.Error(err)
			return
		}

		os.MkdirAll(filepath.Dir(fpath), 0777)

		src = includeReg.ReplaceAllStringFunc(src, DownloadIncludue)

		this.util.WriteFile(fpath, src)
	} else {
		src = this.util.ReadFile(fpath)
	}

	lines := strings.Split(src, "\n")
	is_python := false
	is_shell := false
	is_powershell := false
	if len(lines) > 0 {
		is_python, _ = regexp.MatchString("python", lines[0])
		is_shell, _ = regexp.MatchString("bash", lines[0])
	}

	if strings.HasSuffix(file, ".ps1") {
		is_powershell = true
	}

	os.Chmod(fpath, 0777)
	result := ""
	cmds := []string{
		fpath,
	}
	if is_python {
		cmds = []string{
			"/usr/bin/env",
			"python",
			fpath,
		}
	}
	if is_shell {
		cmds = []string{
			"/bin/bash",
			fpath,
		}
		if debug == "1" {
			cmds = []string{
				"/bin/bash",
				"-x",
				fpath,
			}
		}
	}

	if is_powershell {
		cmds = []string{
			"powershell",
			fpath,
		}
	}

	argvMap := this.util.GetArgsMap()

	if args, ok := argvMap["a"]; ok {
		cmds = append(cmds, strings.Split(args, " ")...)
	} else {
		var args []string
		var tflag bool
		tflag = false
		for i, v := range os.Args {
			if v == "-t" {
				tflag = true
				continue
			}
			if tflag {
				tflag = false
				continue
			}
			if v != "-x" && v != "-u" {
				args = append(args, os.Args[i])
			}
		}
		//fmt.Println("update:",update,"debug:",debug)
		//fmt.Println("args:",args)
		os.Args = args
		cmds = append(cmds, os.Args[6:]...)
		fmt.Println("cmds", cmds)
	}
	result, _, _ = this.util.Exec(cmds, timeout, nil)
	fmt.Println(result)
}

func (this *Cli) Download(module string, action string) {
	argv := this.util.GetArgsMap()
	if filename, ok := argv["f"]; ok {
		var dir string
		var des string
		if d, ok := argv["d"]; ok {
			dir = d
		} else {
			dir = "/"
		}
		if _d, ok := argv["o"]; ok {
			des = _d
		} else {
			des = filename
		}
		req := httplib.Get(this.conf.EnterURL + "/" + this.conf.DefaultModule + "/download")

		req.Param("file", argv["f"])
		req.Param("dir", dir)
		req.ToFile(des)

	} else {
		fmt.Println("-f(filename) is required")
	}

}

func (this *Cli) Upload(module string, action string) {
	argv := this.util.GetArgsMap()
	if filename, ok := argv["f"]; ok {
		var dir string
		if d, ok := argv["d"]; ok {
			dir = d
		}

		req := httplib.Post(this.conf.EnterURL + "/" + this.conf.DefaultModule + "/upload")

		req.Header("auth-uuid", this.util.GetAuthUUID())
		req.PostFile("file", filename)

		if pos := strings.LastIndex(filename, "/"); pos != -1 && !strings.HasSuffix(filename, "/") {
			req.Param("filename", filename[pos+1:])
		} else {
			req.Param("filename", filename)
		}
		req.Param("dir", dir)
		str, err := req.String()
		if err != nil {
			print(err)
		}
		fmt.Println(str)

	} else {
		fmt.Println("-f(filename) is required")
	}

}

func (this *Cli) Adddoc(module string, action string) {

	argv := this.util.GetArgsMap()
	if file, ok := argv["f"]; ok {
		argv["d"] = this.util.ReadFile(file)
	}
	res := this._Request(this.conf.EnterURL+"/"+this.conf.DefaultModule+"/adddoc", argv)
	fmt.Println(res)

}

func (this *Cli) Info(module string, action string) {
	res := make(map[string]string)
	res["version"] = CONST_VERSION
	res["server"] = CLI_SERVER
	fmt.Println(this.util.JsonEncodePretty(res))
}

func (this *Cli) Rand(module string, action string) {
	r := random.New(random.NewSource(time.Now().UnixNano()))
	fmt.Println(r.Float64())
}

func (this *Cli) Lower(module string, action string) {
	_, in := this.StdinJson(module, action)
	fmt.Println(strings.ToLower(in))
}

func (this *Cli) Upper(module string, action string) {
	_, in := this.StdinJson(module, action)
	fmt.Println(strings.ToUpper(in))
}

func (this *Cli) Wlog(module string, action string) {
	m := ""
	l := "info"
	argv := this.util.GetArgsMap()
	if v, ok := argv["m"]; ok {
		m = v
	}
	if m == "" {
		fmt.Println("-m(message) is require, -l(level) info,warn,error")
		return
	}
	if v, ok := argv["l"]; ok {
		l = v
	}
	if l == "warn" {
		log.Warn(m)
	} else if l == "error" {
		log.Error(m)
	} else {
		log.Info(m)
	}
	fmt.Println(m)
	log.Flush()
}

func (this *Cli) Cmd(module string, action string) {
	p := 5
	sleep := 0
	output := "json2"
	ip := ""
	isOutput := false
	var ips []string
	argv := this.util.GetArgsMap()
	if v, ok := argv["p"]; ok {
		p, _ = strconv.Atoi(v)
	}
	if v, ok := argv["sleep"]; ok {
		sleep, _ = strconv.Atoi(v)
	}
	if v, ok := argv["o"]; ok {
		output = v
		isOutput = true
	}
	if v, ok := argv["i"]; ok {
		ip = v
		if _, err := os.Stat(ip); err == nil {
			bip, _ := ioutil.ReadFile(ip)
			exp, _ := regexp.Compile(`[\r\n]+`)
			lines := exp.Split(string(bip), -1)
			for _, line := range lines {
				line = strings.TrimSpace(line)
				if strings.HasPrefix(line, "#") {
					continue
				}
				ips = append(ips, line)
			}
			ip = string(bip)
		} else {
			ips = strings.Split(ip, ",")
		}
	} else {
		message := `
{
  "message":"(error) -i(ip) is require"
}
       `
		fmt.Println(message)
		return
	}
	argv["o"] = output
	argv["sleep"] = fmt.Sprintf("%d", sleep)
	_ = p

	sendCmd := func(argv map[string]string) {
		res := this._Request(this.conf.EnterURL+"/"+this.conf.DefaultModule+"/api", argv)
		if isOutput {
			s := this.util.JsonEncodePretty(res)
			if s != "" {
				fmt.Println(s)
			} else {
				fmt.Println(res)
			}
			return
		}
		rows := this.util.Jq(res, "results")
		message := this.util.Jq(res, "message")
		if message != nil {
			fmt.Println(res)
			return
		}
		var results []string
		switch rows.(type) {
		case []interface{}:
			for _, row := range rows.([]interface{}) {
				switch row.(type) {
				case map[string]interface{}:
					result := row.(map[string]interface{})["result"].(string)
					return_code := fmt.Sprintf("%v", row.(map[string]interface{})["return_code"])
					_ip := row.(map[string]interface{})["i"]
					if strings.HasPrefix(result, "(error)") {
						result = fmt.Sprintf("%s\n%s|failed\n%s\n\n", strings.Repeat("-", 80), _ip, result)
						results = append(results, this.util.Color(result, "yello"))
					} else if return_code == "0" {
						result = fmt.Sprintf("%s\n%s|success\n%s\n\n", strings.Repeat("-", 80), _ip, result)
						results = append(results, this.util.Color(result, "green"))
					} else {
						result = fmt.Sprintf("%s\n%s|failed\n%s\n\n", strings.Repeat("-", 80), _ip, result)
						results = append(results, this.util.Color(result, "red"))
					}

				}
			}
		}
		fmt.Println(strings.Join(results, "\n"))
	}
	var bips []string
	for _, _ip := range ips {
		bips = append(bips, _ip)
		if len(bips) >= p {
			argv["i"] = strings.Join(bips, ",")
			sendCmd(argv)
			if sleep > 0 {
				time.Sleep(time.Second * time.Duration(sleep))
			}
			bips = []string{}
		}
	}
	if len(bips) > 0 {
		argv["i"] = strings.Join(bips, ",")
		sendCmd(argv)
	}
}

func (this *Cli) Color(module string, action string) {
	m := ""
	c := "green"
	argv := this.util.GetArgsMap()
	if v, ok := argv["m"]; ok {
		m = v
	}
	if v, ok := argv["c"]; ok {
		c = v
	}
	fmt.Println(this.util.Color(m, c))
}

func (this *Cli) Randstr(module string, action string) {
	l := 10
	argv := this.util.GetArgsMap()
	if v, ok := argv["l"]; ok {
		l, _ = strconv.Atoi(v)
	}

	var src []int

	for i := 65; i < 97; i++ {
		src = append(src, i)
	}
	var ret []string
	r := random.New(random.NewSource(time.Now().UnixNano()))
	for i := 0; i < l; i++ {
		_ = src
		ret = append(ret, string(src[r.Intn(26)]))
	}
	fmt.Println(strings.Join(ret, ""))
}

func (this *Cli) Uuid(module string, action string) {
	id := this.util.GetUUID()
	fmt.Println(id)
}

func (this *Cli) Randint(module string, action string) {
	start := 0
	end := 100
	argv := this.util.GetArgsMap()
	if v, ok := argv["r"]; ok {
		ss := strings.Split(v, ":")
		if len(ss) == 2 {
			start, _ = strconv.Atoi(ss[0])
			end, _ = strconv.Atoi(ss[1])
		}

	}

	RandInt := func(min, max int) int {
		r := random.New(random.NewSource(time.Now().UnixNano()))
		if min >= max {
			return max
		}
		return r.Intn(max-min) + min
	}

	fmt.Println(RandInt(start, end))

}

func (this *Cli) Md5(module string, action string) {

	s := ""
	fn := ""
	argv := this.util.GetArgsMap()
	if v, ok := argv["s"]; ok {
		s = v
		fmt.Println(this.util.MD5(s))
		return
	}
	if v, ok := argv["f"]; ok {
		fn = v
	}
	if fn != "" {
		fmt.Println(this.util.MD5File(fn))
		return
	}
	_, s = this.StdinJson(module, action)
	fmt.Println(this.util.MD5(s))

}

func (this *Cli) Cut(module string, action string) {

	s := ""
	start := 0
	end := -1
	argv := this.util.GetArgsMap()
	if v, ok := argv["s"]; ok {
		s = v
	}
	if s == "" {
		s = this.StdioStr(module, action)

	}
	if v, ok := argv["p"]; ok {
		ss := strings.Split(v, ":")
		if len(ss) == 2 {
			start, _ = strconv.Atoi(ss[0])
			if ss[1] != "" {
				end, _ = strconv.Atoi(ss[1])
			} else {
				end = len(s)
			}
		}
		if len(ss) == 1 {
			start, _ = strconv.Atoi(ss[0])
			end = len(s)
		}

	} else {
		end = len(s)
	}

	fmt.Println(s[start:end])

}

func (this *Cli) Split(module string, action string) {

	s := ""
	sep := ","

	argv := this.util.GetArgsMap()

	if v, ok := argv["s"]; ok {
		sep = v
	}

	if s == "" {
		s = this.StdioStr(module, action)

	}

	if reg, err := regexp.Compile(sep); err == nil {
		ss := reg.Split(s, -1)
		fmt.Println(this.util.JsonEncodePretty(ss))
	} else {
		fmt.Println(s)
	}

}

func (this *Cli) StdioStr(module string, action string) string {
	var lines []string
	input := bufio.NewScanner(os.Stdin)
	for input.Scan() {
		lines = append(lines, input.Text())
	}
	return strings.Join(lines, "\n")

}

func (this *Cli) Replace(module string, action string) {

	o := ""
	s := ""
	n := ""

	argv := this.util.GetArgsMap()

	if v, ok := argv["o"]; ok {
		o = v
	}
	if v, ok := argv["s"]; ok {
		s = v
	}
	if v, ok := argv["n"]; ok {
		n = v
	}

	if s == "" {
		s = this.StdioStr(module, action)
		//_, s = this.StdinJson(module, action)

	}
	reg := regexp.MustCompile(o)
	fmt.Println(reg.ReplaceAllString(s, n))
}

func (this *Cli) Match(module string, action string) {

	m := ""
	o := ""
	s := ""

	is_all := false

	argv := this.util.GetArgsMap()
	if v, ok := argv["m"]; ok {
		m = v
	}
	if v, ok := argv["o"]; ok {
		o = v
	}
	if v, ok := argv["s"]; ok {
		s = v
	}

	if s == "" {
		_, s = this.StdinJson(module, action)

	}
	for i := 0; i < len(o); i++ {
		if string(o[i]) == "i" {
			m = "(?i)" + m
		}
		if string(o[i]) == "a" || string(o[i]) == "m" {
			is_all = true
		}
	}

	if reg, err := regexp.Compile(m); err == nil {

		if is_all {
			ret := reg.FindAllString(s, -1)
			if len(ret) > 0 {
				fmt.Println(this.util.JsonEncodePretty(ret))
			} else {
				fmt.Println("")
			}
		} else {
			ret := reg.FindString(s)
			fmt.Println(ret)
		}

	}

}

func (this *Cli) Keys(module string, action string) {

	obj, _ := this.StdinJson(module, action)
	var keys []string
	switch obj.(type) {
	case map[string]interface{}:
		for k, _ := range obj.(map[string]interface{}) {
			keys = append(keys, k)
		}
	}
	fmt.Println(this.util.JsonEncodePretty(keys))
}

func (this *Cli) Len(module string, action string) {

	obj, in := this.StdinJson(module, action)
	switch obj.(type) {
	case []interface{}:
		fmt.Println(len(obj.([]interface{})))
		return

	case map[string]interface{}:
		i := 0
		for _ = range obj.(map[string]interface{}) {
			i = i + 1
		}
		fmt.Println(i)
		return
	}

	fmt.Println(len(in))
}

func (this *Cli) Kvs(module string, action string) {

	obj, _ := this.StdinJson(module, action)
	var keys []string
	switch obj.(type) {
	case map[string]interface{}:
		for k, v := range obj.(map[string]interface{}) {
			switch v.(type) {
			case map[string]interface{}, []interface{}:
				if b, e := json.Marshal(v); e == nil {
					s := strings.Replace(string(b), "\\", "\\\\", -1)
					s = strings.Replace(s, "\"", "\\\"", -1)
					keys = append(keys, fmt.Sprintf(k+"=\"%s\"", s))
				}
			default:
				keys = append(keys, fmt.Sprintf(k+"=\"%s\"", v))
			}
		}
	case []interface{}:
		for i, v := range obj.([]interface{}) {

			keys = append(keys, fmt.Sprintf("a%d=\"%s\"", i, v))

		}

	}
	fmt.Println(strings.Join(keys, "\n"))
}

func (this *Cli) Join(module string, action string) {

	obj, _ := this.StdinJson(module, action)
	sep := ","
	wrap := ""
	trim := ""
	argv := this.util.GetArgsMap()
	if v, ok := argv["s"]; ok {
		sep = v
	}
	if v, ok := argv["t"]; ok {
		trim = v
	}
	if v, ok := argv["w"]; ok {
		wrap = v
	}
	var lines []string
	switch obj.(type) {
	case []interface{}:
		for _, v := range obj.([]interface{}) {
			if trim != "" {
				if v == nil || fmt.Sprintf("%s", v) == "" {
					continue
				}
			}
			if wrap != "" {
				lines = append(lines, fmt.Sprintf("%s%s%s", wrap, v, wrap))
			} else {
				lines = append(lines, fmt.Sprintf("%s", v))
			}
		}
	}
	fmt.Println(strings.Join(lines, sep))

}

func (this *Cli) Sqlite(module string, action string) {
	var (
		err      error
		v        interface{}
		s        string
		isUpdate bool
		s2       string
		rows     []map[string]interface{}
		count    int64
		db       *sql.DB
	)

	f := ""
	t := "data"
	h := `
   -s sql
   -f filename
   -t tablename
`
	argv := this.util.GetArgsMap()
	if v, ok := argv["f"]; ok {
		f = v
	}

	if _, ok := argv["h"]; ok || len(argv) == 0 {
		fmt.Println(h)
		return
	}
	if v, ok := argv["t"]; ok {
		t = v
	}
	if v, ok := argv["s"]; ok {
		s = v
	}
	if s == "" {
		v, s = this.StdinJson(module, action)
	}
	_ = s
	if s == "" {
		fmt.Println("(error) -s input null")
		return
	}

	s2 = strings.TrimSpace(strings.ToLower(s))
	if strings.HasPrefix(s2, "select") {
		isUpdate = false
	}

	if v != nil {
		if db, err = this.util.SqliteInsert(f, t, v.([]interface{})); err != nil {
			log.Error(err)
			fmt.Println(err)
			return
		}
		_ = db
		fmt.Println("ok")
		return
	}
	if !isUpdate {

		count, err = this.util.SqliteExec(f, s)

		if err != nil {
			log.Error(err)
			fmt.Println(err)
			return
		}
		fmt.Println(fmt.Sprintf("ok(%d)", count))

	} else {
		rows, err = this.util.SqliteQuery(f, s)
		if err != nil {
			fmt.Println(err)
			return
		}
		fmt.Println(this.util.JsonEncodePretty(rows))
	}
}

func (this *Cli) Pq(module string, action string) {
	var (
		err   error
		dom   *goquery.Document
		title string
		href  string
		ok    bool
		text  string
		html  string
	)
	u := ""
	s := "html"
	m := "text"
	f := ""
	c := ""
	a := "link"

	argv := this.util.GetArgsMap()
	if v, ok := argv["f"]; ok {
		f = v
	}
	if v, ok := argv["s"]; ok {
		s = v
	}
	if v, ok := argv["m"]; ok {
		m = v
	}

	if v, ok := argv["a"]; ok {
		a = v
	}

	if f != "" {

		c = this.util.ReadFile(f)

	}

	if c == "" {
		var lines []string
		input := bufio.NewScanner(os.Stdin)
		for input.Scan() {
			lines = append(lines, input.Text())
		}
		c = strings.Join(lines, "")
	}

	_ = c
	_ = m
	_ = s
	_ = u
	_ = err

	dom, err = goquery.NewDocumentFromReader(strings.NewReader(c))

	var result []interface{}
	dom.Find(s).Each(func(i int, selection *goquery.Selection) {

		if a == "link" {
			if href, ok = selection.Attr("href"); ok {
				title = selection.Text()
				item := make(map[string]string)
				item["href"] = strings.TrimSpace(href)
				item["title"] = strings.TrimSpace(title)
				result = append(result, item)
			}
		} else if a == "table" {
			var rows []string
			selection.Find("table tr").Each(func(i int, selection *goquery.Selection) {
				var row []string
				selection.Find("td").Each(func(i int, selection *goquery.Selection) {
					row = append(row, strings.TrimSpace(selection.Text()))
				})
				rows = append(rows, strings.Join(row, "######"))
			})

			result = append(result, strings.Join(rows, "$$$$$"))

		} else {

			if m == "text" {
				text = selection.Text()
				result = append(result, text)
			}
			if m == "html" {
				html, err = selection.Html()
				result = append(result, html)
			}
		}
	})

	fmt.Println(this.util.JsonEncodePretty(result))

}

func (this *Cli) Json_val(module string, action string) {
	this.Jq(module, action)
}

func (this *Cli) Jq(module string, action string) {

	data, _ := this.StdinJson(module, action)
	if data == nil {
		return
	}
	key := ""
	var obj interface{}
	argv := this.util.GetArgsMap()
	if v, ok := argv["k"]; ok {
		key = v
	}
	var ks []string
	if strings.Contains(key, ",") {
		ks = strings.Split(key, ",")
	} else {
		ks = strings.Split(key, ".")
	}

	obj = data

	ParseDict := func(obj interface{}, key string) interface{} {
		switch obj.(type) {
		case map[string]interface{}:
			if v, ok := obj.(map[string]interface{})[key]; ok {
				return v
			}
		}
		return nil

	}

	ParseList := func(obj interface{}, key string) interface{} {
		var ret []interface{}
		switch obj.(type) {
		case []interface{}:
			if ok, _ := regexp.MatchString("^\\d+$", key); ok {
				i, _ := strconv.Atoi(key)
				return obj.([]interface{})[i]
			}

			for _, v := range obj.([]interface{}) {
				switch v.(type) {
				case map[string]interface{}:
					if key == "*" {
						for _, vv := range v.(map[string]interface{}) {
							ret = append(ret, vv)
						}
					} else {
						if vv, ok := v.(map[string]interface{})[key]; ok {
							ret = append(ret, vv)
						}
					}
				case []interface{}:
					if key == "*" {
						for _, vv := range v.([]interface{}) {
							ret = append(ret, vv)
						}
					} else {
						ret = append(ret, v)
					}
				}
			}
		}
		return ret
	}
	if key != "" {
		for _, k := range ks {
			switch obj.(type) {
			case map[string]interface{}:
				obj = ParseDict(obj, k)
			case []interface{}:
				obj = ParseList(obj, k)
			}
		}
	}

	switch obj.(type) {
	case map[string]interface{}, []interface{}:
		fmt.Println(this.util.JsonEncodePretty(obj))
	default:
		fmt.Println(obj)
	}

}

func (this *Cli) Jf(module string, action string) {

	data, _ := this.StdinJson(module, action)

	c := "*"
	w := "1=1"
	s := "select %s from data where 1=1 and %s %s"

	limit := ""
	argv := this.util.GetArgsMap()
	if v, ok := argv["c"]; ok {
		c = v
	}

	if v, ok := argv["w"]; ok {
		w = v
	}

	if v, ok := argv["limit"]; ok {
		limit = " limit " + v
	}

	db, err := sql.Open("sqlite3", ":memory:")
	if err != nil {
		log.Error(err)
		log.Flush()
		return
	}

	Push := func(db *sql.DB, records []interface{}) error {
		hashKeys := map[string]struct{}{}

		keyword := []string{"ALTER",
			"CLOSE",
			"COMMIT",
			"CREATE",
			"DECLARE",
			"DELETE",
			"DENY",
			"DESCRIBE",
			"DOMAIN",
			"DROP",
			"EXECUTE",
			"EXPLAN",
			"FETCH",
			"GRANT",
			"INDEX",
			"INSERT",
			"OPEN",
			"PREPARE",
			"PROCEDURE",
			"REVOKE",
			"ROLLBACK",
			"SCHEMA",
			"SELECT",
			"SET",
			"SQL",
			"TABLE",
			"TRANSACTION",
			"TRIGGER",
			"UPDATE",
			"VIEW",
			"GROUP"}

		_ = keyword

		//for _, record := range records {
		//	switch record.(type) {
		//	case map[string]interface{}:
		//		for key, _ := range record.(map[string]interface{}) {
		//			key2 := key
		//			if this.util.Contains(strings.ToUpper(key), keyword) {
		//				key2 = "_" + key
		//				record.(map[string]interface{})[key2] = record.(map[string]interface{})[key]
		//				delete(record.(map[string]interface{}), key)
		//			}
		//			hashKeys[key2] = struct{}{}
		//		}
		//	}
		//}

		for _, record := range records {
			switch record.(type) {
			case map[string]interface{}:
				for key, _ := range record.(map[string]interface{}) {
					if strings.HasPrefix(key, "`") {
						continue
					}
					key2 := fmt.Sprintf("`%s`", key)
					record.(map[string]interface{})[key2] = record.(map[string]interface{})[key]
					delete(record.(map[string]interface{}), key)
					hashKeys[key2] = struct{}{}
				}
			}
		}

		keys := []string{}

		for key, _ := range hashKeys {
			keys = append(keys, key)
		}
		//		db.Exec("DROP TABLE data")
		query := "CREATE TABLE data (" + strings.Join(keys, ",") + ")"
		if _, err := db.Exec(query); err != nil {
			log.Error(query)
			log.Flush()
			return err
		}

		for _, record := range records {
			recordKeys := []string{}
			recordValues := []string{}
			recordArgs := []interface{}{}

			switch record.(type) {
			case map[string]interface{}:

				for key, value := range record.(map[string]interface{}) {
					recordKeys = append(recordKeys, key)
					recordValues = append(recordValues, "?")
					recordArgs = append(recordArgs, value)
				}

			}

			query := "INSERT INTO data (" + strings.Join(recordKeys, ",") +
				") VALUES (" + strings.Join(recordValues, ", ") + ")"

			statement, err := db.Prepare(query)
			if err != nil {
				log.Error(err, "can't prepare query: %s", query, recordKeys, recordArgs, recordValues)
				log.Flush()
				continue

			}

			_, err = statement.Exec(recordArgs...)
			if err != nil {
				log.Error(
					err, "can't insert record",
				)

			}
			statement.Close()
		}

		return nil
	}

	switch data.(type) {
	case []interface{}:
		err = Push(db, data.([]interface{}))
		if err != err {
			fmt.Println(err)
			return
		}
	default:
		msg := "(error) just support list"
		fmt.Println(msg)
		log.Error(msg)
		return

	}

	defer db.Close()
	if err == nil {
		db.SetMaxOpenConns(1)
	} else {
		log.Error(err.Error())
	}

	s = fmt.Sprintf(s, c, w, limit)

	rows, err := db.Query(s)

	if err != nil {
		log.Error(err, s)
		log.Flush()
		fmt.Println(err)
		return
	}
	defer rows.Close()

	records := []map[string]interface{}{}
	for rows.Next() {
		record := map[string]interface{}{}

		columns, err := rows.Columns()
		if err != nil {
			log.Error(
				err, "unable to obtain rows columns",
			)
			continue
		}

		pointers := []interface{}{}
		for _, column := range columns {
			var value interface{}
			pointers = append(pointers, &value)
			record[column] = &value
		}

		err = rows.Scan(pointers...)
		if err != nil {
			log.Error(err, "can't read result records")
			continue
		}

		for key, value := range record {
			indirect := *value.(*interface{})
			if value, ok := indirect.([]byte); ok {
				record[key] = string(value)
			} else {
				record[key] = indirect
			}
		}

		records = append(records, record)
	}

	fmt.Println(util.JsonEncodePretty(records))

}

func (this *Cli) StdinJson(module string, action string) (interface{}, string) {

	var lines []string
	input := bufio.NewScanner(os.Stdin)
	for input.Scan() {
		lines = append(lines, input.Text())
	}
	in := strings.Join(lines, "")
	var obj interface{}
	if err := json.Unmarshal([]byte(in), &obj); err != nil {
		log.Error(err, in)
		obj = nil
	}
	return obj, in
}

func (this *Cli) Rexec(module string, action string) {
	user, password := this._UserInfo()
	data := map[string]string{
		"u": user,
		"p": password,
	}
	res := this._Request(this.conf.EnterURL+"/"+this.conf.DefaultModule+"/rexec", data)
	fmt.Println(res)

}

func (this *Cli) Run() {
	if this.util.IsExist("uuids") {

		uuids := this.util.ReadFile("uuids")
		BENCHMARK = true

		for i, uuid := range strings.Split(uuids, "\n") {
			uuid = strings.TrimSpace(uuid)
			go this.Heartbeat(uuid)
			go this.WatchEtcd(uuid)
			go this.DealCommands(uuid)
			fmt.Println(fmt.Sprintf("No:%v UUID:%v", i, uuid))

		}

	} else {
		go this.Heartbeat("")
		go this.WatchEtcd("")
		for i := 0; i < 30; i++ {
			go this.DealCommands("")
		}
	}

	getMem := func() uint64 {
		var ms runtime.MemStats
		runtime.ReadMemStats(&ms)
		return ms.HeapAlloc / 1024 / 1024
	}

	go func() {
		this.util.ExecCmd([]string{"cli shell -d system -f install_cli_sdk.py"}, 10)
		this.stop()
		for {
			mpids := make(map[string]string)
			pids := this.getPids()
			for _, pid := range pids {
				mpids[pid] = pid
			}
			mpids[fmt.Sprintf("%d", os.Getpid())] = fmt.Sprintf("%d", os.Getpid())
			var pps []string
			for k, _ := range mpids {
				if strings.TrimSpace(k) != "" {
					pps = append(pps, k)
				}
			}
			if fp, err := os.OpenFile(PID_FILE, os.O_CREATE|os.O_RDWR, 0644); err == nil {
				fp.WriteString(fmt.Sprintf("%s", strings.Join(pps, "\n")))
				fp.Close()
			} else {
				log.Error(err.Error())
				fmt.Println(err.Error())
			}
			if getMem() > 500 {
				log.Warn("cli process suicide...")
				os.Exit(1)
			}
			this.isRunning()
			if this.util.RandInt(0, 30) < 3 {
				this.killPython()
			}
			time.Sleep(time.Second * 60)

		}
	}()

	select {}
}

func (this *Cli) Httpserver(module string, action string) {

	argv := this.util.GetArgsMap()

	host := this.util.GetLocalIP()
	port := "8000"
	root := "/"
	if v, err := this.util.Home(); err == nil {
		root = v
	}

	if v, ok := argv["p"]; ok {
		port = v

	}

	if v, ok := argv["h"]; ok {
		host = v

	}

	if v, ok := argv["d"]; ok {
		root = v
	}

	h := http.FileServer(http.Dir(root))
	fmt.Println(fmt.Sprintf("http server listen %s:%s", host, port))
	err := http.ListenAndServe(fmt.Sprintf("%s:%s", host, port), h)

	if err != nil {
		log.Error("Error starting http server:", err)
		fmt.Println(err)
	}

}

func (this *Cli) Ftpserver(module string, action string) {

	argv := this.util.GetArgsMap()
	user := "root"
	pass := this.util.GetProductUUID()
	host := this.util.GetLocalIP()
	port := 2121
	root := "/"
	if v, err := this.util.Home(); err == nil {
		root = v
	}
	if v, ok := argv["u"]; ok {
		user = v
	}
	if v, ok := argv["h"]; ok {
		host = v
	}
	if v, ok := argv["p"]; ok {
		pass = v
	}
	if v, ok := argv["P"]; ok {
		port, _ = strconv.Atoi(v)

	}

	if v, ok := argv["d"]; ok {
		root = v
	}

	factory := &filedriver.FileDriverFactory{
		RootPath: root,
		Perm:     server.NewSimplePerm("user", "group"),
	}

	opts := &server.ServerOpts{
		Factory:  factory,
		Port:     port,
		Hostname: host,
		Auth:     &server.SimpleAuth{Name: user, Password: pass},
	}

	ftp := server.NewServer(opts)

	err := ftp.ListenAndServe()
	if err != nil {
		log.Error("Error starting ftp server:", err)
	}

}

func (this *Cli) Downlaod(module string, action string) {

	argv := this.util.GetArgsMap()

	if filename, ok := argv["f"]; ok {
		var dir string
		var out string
		if d, ok := argv["d"]; ok {
			dir = d
		}
		if v, ok := argv["o"]; ok {
			out = v
		}
		out = filename
		req := httplib.Post(this.conf.EnterURL + "/" + this.conf.DefaultModule + "/" + action)

		req.Param("file", filename)
		req.Param("dir", dir)
		err := req.ToFile(out)
		if err != nil {
			log.Error(err)
			print(err)
		}

	} else {
		fmt.Println("-f(filename) is required")
	}

}

func print(args ...interface{}) {

	fmt.Println(args)

}

type Daemon struct {
	daemon.Daemon
}

func (this *Daemon) Manage(cli *Cli) (string, error) {

	usage := "Usage: cli daemon -s [install | remove | start | stop | status| restart |debug]"

	// if received any kind of command, do it
	var command string
	if len(os.Args) > 3 {
		command = os.Args[3]
		//print(command)
		switch command {
		case "install":
			return this.Install(" daemon -s daemon ")
		case "remove":
			return this.Remove()
		case "start":
			return this.Start()
		case "daemon":

			print("daemon")
		case "debug":
			select {}
		case "stop":
			return this.Stop()
		case "status":
			return this.Status()
		case "restart":
			this.Stop()
			return this.Start()
		default:
			return usage, nil
		}
	} else {
		return usage, nil
	}

	go cli.Heartbeat("")
	time.Sleep(time.Second * 3)
	go cli.WatchEtcd("")
	go cli.DealCommands("")

	for {
		time.Sleep(time.Second * 5)
	}

	return usage, nil
}

func initHttpLib() {

	defaultTransport := &http.Transport{
		DisableKeepAlives:   true,
		Dial:                httplib.TimeoutDialer(time.Second*15, time.Second*300),
		MaxIdleConns:        100,
		MaxIdleConnsPerHost: 100,
	}
	settins := httplib.BeegoHTTPSettings{
		UserAgent:        "Go-FastDFS",
		ConnectTimeout:   15 * time.Second,
		ReadWriteTimeout: 120 * time.Second,
		Gzip:             true,
		DumpBody:         true,
		Transport:        defaultTransport,
	}
	httplib.SetDefaultSetting(settins)

}

func initCron() {
	defer func() {
		if re := recover(); re != nil {
			buffer := debug.Stack()
			log.Error(string(buffer))
			log.Flush()
		}
	}()
	var err error
	engine, err = xorm.NewEngine("sqlite3", CLI_DB_FILE)
	if err != nil {
		log.Error(err.Error())
		return
	}
	//engine.ShowSQL(true)
	if err = engine.Sync2(new(TCron)); err != nil {
		log.Error(err.Error())
	}
	engine.Exec("CREATE UNIQUE INDEX `UQE_t_cron_cron` ON `t_cron` (`Fcron`,`Fjob`);")
	cache := make(map[int]TCron)
	ip := cli.util.GetLocalIP()

	refreshFromServer := func() {
		data := make(map[string]string)
		data["i"] = ip
		data["a"] = "list"
		data["uuid"] = cli.util.GetProductUUID()
		result := cli.util.Request(cli.conf.EnterURL+"/cli/cron", data)
		var crons []TCron
		if err := json.Unmarshal([]byte(result), &crons); err != nil {
			log.Error(err)
			return
		}

		mds := mapset.NewSet()
		for _, c := range crons {
			mds.Add(c.Fmd5)
		}
		var _crons []TCron

		_mds := mapset.NewSet()
		err := engine.Where("1=1").Find(&_crons)
		if err != nil {
			log.Error(err)
			return
		}
		for _, c := range _crons {
			_mds.Add(c.Fmd5)
		}

		if !mds.Equal(_mds) {
			log.Info("reset cron ", mds, _mds)
			entries := cronTab.Entries()
			for _, entry := range entries {
				cronTab.Remove(entry.ID)
			}
			engine.Where("1=1").Delete(&TCron{})
			for _, c := range crons {
				if _, err := engine.Insert(&c); err != nil {
					fmt.Println(err)
					log.Error(err)
				}
			}
			cache = make(map[int]TCron)
		} else {
			for _, c := range crons {
				engine.Cols("Fenable", "Furl", "Fip", "Fdesc", "Ftimeout", "Fcron", "Fjob").Where("Fmd5=?", c.Fmd5).Update(&c)
			}
		}

	}

	refreshJob := func() {
		jobs := make([]TCron, 0)
		err = engine.Where("1=1").Find(&jobs)
		if err != nil {
			log.Error(err.Error())
			return
		}
		for k, job := range cache { //delete from db
			exist := false
			for _, _job := range jobs {
				if _job.Fid == k {
					exist = true
					break
				}
			}
			if !exist {
				cronTab.Remove(cron.EntryID(job.Fpid))
			}
		}
		for _, job := range jobs { // add job not exist
			if job.Fenable != 1 {
				cronTab.Remove(cron.EntryID(job.Fpid))
				delete(cache, job.Fid)
				continue
			}
			//md5str:=cli.util.MD5( fmt.Sprintf("%s,%s,%s",ip, job.Fcron,job.Fjob))
			if _job, ok := cache[job.Fid]; ok {
				if job.Fenable == _job.Fenable {
					continue
				} else {
					cronTab.Remove(cron.EntryID(_job.Fpid))
				}
			}
			j := func(job TCron) cron.FuncJob {
				jj := func() {
					defer func() {
						if re := recover(); re != nil {
							buffer := debug.Stack()
							log.Error(string(buffer))
							log.Flush()
						}
					}()
					result := cli.util.ExecCmd([]string{job.Fjob}, job.Ftimeout)
					log.Info(fmt.Sprintf("cron md5:%s  result:%s", job.Fmd5, result))
					if job.Furl != "" {
						data := make(map[string]string)
						data["result"] = result
						data["ip"] = ip
						cli.util.Request(job.Furl, data)
					}
					job.FlastUpdate = time.Now().Format("2006-01-02 15:04:05")
					if len(result) > 10240 {
						job.Fresult = result[0:10240]
					} else {
						job.Fresult = result
					}
					if _, err := engine.Where("Fid=?", job.Fid).Cols("flast_update", "Fresult").Update(job); err != nil {
						log.Error(err.Error())
					}
				}
				return cron.FuncJob(jj)
			}
			_j := j(job)
			if jobId, err := cronTab.AddFunc(job.Fcron, _j); err != nil {
				log.Error(err.Error(), job)
				job.Fpid = 0
			} else {
				job.Fpid = int(jobId)
				cache[job.Fid] = job
				log.Info(jobId, job)
			}
			//job.Fmd5=md5str
			job.FlastUpdate = time.Now().Format("2006-01-02 15:04:05")
			if _, err := engine.Cols("Fmd5", "flast_update", "Fpid").Where("Fid=?", job.Fid).Update(job); err != nil {
				log.Error(err.Error())
			}

		}
	}

	cronTab.Start()
	go func() {
		for {
			time.Sleep(time.Second * time.Duration(cli.util.RandInt(5, 10)))
			refreshJob()
			if len(cronTab.Entries()) != len(cache) {
				log.Warn("jobs:", len(cronTab.Entries()), len(cache))
			}
			time.Sleep(time.Second * time.Duration(cli.util.RandInt(30, 60)))
		}
	}()

	go func() {
		for {
			refreshFromServer()
			//time.Sleep(time.Second*10)
			time.Sleep(time.Second * time.Duration(cli.util.RandInt(30, 60)))
		}
	}()
}

func init() {

	//	user, err := user.Current()
	//	if err == nil {
	//		logger.SetRollingFile(user.HomeDir+"/cli_log", "cli.log", 10, 1, logger.MB)
	//		logger.SetLevel(log.Debug)
	//	}

	os.MkdirAll("/var/log/", 07777)
	os.MkdirAll("/var/lib/cli", 07777)

	initHttpLib()

	logger, err := log.LoggerFromConfigAsBytes([]byte(logConfigStr))

	if err != nil {
		log.Error(err)
		panic("init log fail")
	}

	log.ReplaceLogger(logger)
}

type AA struct {
	Name string `json:"name"`
	Age  int    `json:"age"`
}

func sigHandle() {
	c := make(chan os.Signal)
	signal.Notify(c, syscall.SIGKILL)
	go func() {
		for s := range c {
			switch s {
			case syscall.SIGHUP, syscall.SIGINT, syscall.SIGTERM, syscall.SIGQUIT, syscall.SIGKILL:
				log.Info("退出", s)
				os.Exit(1)
			}
		}
	}()
}

func main() {

	cli.conf.IP = cli.util.GetLocalIP()
	cli.conf.UUID = cli.util.GetProductUUID()
	obj := reflect.ValueOf(cli)
	//_daemon, err := daemon.New("cli", "cli daemon")
	//if err != nil {
	//	log.Error(err)
	//}
	//daemon := &Daemon{_daemon}
	//cli._daemon = daemon

	//cli.util.SetCliValByKey("server", CLI_SERVER)

	//sigHandle()

	if os.Getenv("CLI_SERVER") != "" {
		CLI_SERVER = os.Getenv("CLI_SERVER")
		cli.util.SetCliValByKey("server", CLI_SERVER)
	}

	server := cli.util.GetCliValByKey("server")

	if server == "" || strings.Contains(server, "127.0.0.1") {
		if CLI_SERVER != "" && strings.HasPrefix(server, "http") {
			cli.util.SetCliValByKey("server", CLI_SERVER)
		}
	}

	module := cli.util.GetModule(cli.conf)
	action := cli.util.GetAction(cli.conf)

	if len(os.Args) == 1 {
		cli.Help(module, action)
		return
	}

	for i := 0; i < obj.NumMethod(); i++ {
		if obj.MethodByName(strings.Title(action)).IsValid() {
			obj.MethodByName(strings.Title(action)).Call([]reflect.Value{reflect.ValueOf(module), reflect.ValueOf(action)})
			break
		} else if i == obj.NumMethod()-1 {
			obj.MethodByName("Default").Call([]reflect.Value{reflect.ValueOf(module), reflect.ValueOf(action)})
		}
	}

}

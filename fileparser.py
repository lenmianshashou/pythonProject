'''
     Contact: Pengpeng Jiang, 03A312 (Shanghai - Derek Cheng), EXT
     Date: 07/19/2018
     Version:1.04
'''
import re,sys,os,json
import cPickle as pickle
from collections import defaultdict
from operator import itemgetter, attrgetter
import os,subprocess
import glob
###home made module
from metrics import gzopen
import getshape
from mkdir import *
class fileparser(object):
    def __init__(self):
        #script will auto generate file : self.username + rpt directory for you and gzip when exited
        self.username =  os.popen("who | cut -d' ' -f1 | sort | uniq").readlines()[0].strip()
        #self.log = logging_amd.logging_amd(file_name = 'fileparser.log')
        #self.log.console.setLevel(logging.CRITICAL)

    def parser_netconn(self):
        '''
        Format:
            net:AON_SMUIO_PWROK                                                                  type:signal      #instTerms:2    #terms:0 
            driver:vdci_nbio_right_t/AON_SMUIO_PWROK_soc
            load:smu_fuse_smuio_pwr_t/AON_SMUIO_PWROK
        Varibles:
            self.dic_net2driv = {}
            self.dic_net2load = {}
            self.dic_net2attr = {} #net:(type,instTerms)
        Func:
            nets = filter_net(driv,load)
        '''
        pass

    def parser_netconn2(self):
        '''
        With less infomation compared with class parser_netconn, but it can save time
        Format:
            net:AON_SMUIO_PWROK                                                                  type:signal      #instTerms:2    #terms:0 
            driver:vdci_nbio_right_t/AON_SMUIO_PWROK_soc
            load:smu_fuse_smuio_pwr_t/AON_SMUIO_PWROK
        Varibles:
            self.dic_net2driv = {}
            self.dic_net2load = {}
            self.dic_net2attr = {} #net:(type,instTerms)
        Func:
            nets = filter_net(driv,load)
        '''
        pass

    def parser_feedconn(self):
        '''
        Format:
            net:gc__SE3SH0DB0_SE3SH0DB2_dbrmirdreq_addr[14]                                          #terms:0  #instTerms:4
            driv:gc_db_t300/DBro_dbrmirdreq_addr[14]                                               net:gc__SE3SH0DB0_SE3SH0DB2_dbrmirdreq_addr[14]
            load:gc_rmi_t31/FE_FEEDX_MFT__0__gc_db_1_t_0__gc_rmi_t_0__gc__SE0SH0DB3_SE0SH0DB1_dbrmirdreq_addr__14__AMD_gc_rmi_t_0net:gc__SE3SH0DB0_SE3SH0DB2_dbrmirdreq_addr[14]
            driv:gc_rmi_t31/FE_FEEDX_MFT__1__gc_rmi_t_0__gc_db_0_t_0__gc__SE0SH0DB3_SE0SH0DB1_dbrmirdreq_addr__14__AMD_gc_rmi_t_0net:FE_FEEDX_MFT__1__gc_rmi_t_7__gc_db_0_t_7__gc__SE3SH0DB0_SE3SH0DB2_dbrmirdreq_addr__14
            load:gc_db_t302/DBri_dbrmirdreq_addr[14]                                               net:FE_FEEDX_MFT__1__gc_rmi_t_7__gc_db_0_t_7__gc__SE3SH0DB0_SE3SH0DB2_dbrmirdreq_addr__14 

        Varibles:
            self.dic_net2feed = defaultdict(list)
        '''
        pass


    def parser_xml(self):
        '''
            Format:
                1.##################################
                <rep constraint="EQ 0" container="CHIP" contract="65" domain="Cpl_FCLK" file="bia_repeaters_tiles.xml" negedge="false" rep_inst="CHIP_rep_Cpl_FCLK" scan_balance="false" scanned="" sdc_clk="FCLK">
                <net bundle="vdci2_gc_df20_df_SdpVdci" fgcg_ctrl="false" name="vdci2_gc_df20_df_SdpVdci_Empty" orig_bundle="vdci2_gc_df20_df_SdpVdci" rep_type="rep" />
                <net bundle="vdci2_gc_df20_df_SdpVdci" fgcg_ctrl="false" name="vdci2_gc_df20_df_SdpVdci_OrigDataCkEnRcv" orig_bundle="vdci2_gc_df20_df_SdpVdci" rep_type="rep" />
                <bundle name="vdci2_gc_df20_df_SdpVdci" orig_name="vdci2_gc_df20_df_SdpVdci" protocol="NULL" />
                </rep>
                2.#######################
                  <tile_flavor flavor="compute_array" tile="compute_array">
                    <clock domain="GC_Shift_Clk" root="Cpl_GFXCLK" sdc_clk="GC_SHIFT_CLK" />
                    <clock domain="Cpl_GFXCLK" root="Cpl_GFXCLK" sdc_clk="GFXCLK" />
                    <clock domain="cgcg_Cpl_GFXCLK" root="Cpl_GFXCLK" sdc_clk="GFXCLK" />
                    <instance name="compute_array0">
                      <sdc_clk name="GC_SHIFT_CLK" />
                      <sdc_clk name="GFXCLK" />
                    </instance>
                    ....
                  </tile_flavor>
            Varibles:
                self.dic_cont2num    = {}  #hash:contractor to constraint
                self.dic_bundle2net  = defaultdict(list)  #hash: bundle to net.
                self.dic_cont2bundle = defaultdict(list)  #hash: contractor to bundle
                self.dic_bundle2num  = {}  #hash: bundle to constraint
                self.dic_net         = {}  #hash: net to None. Just to transvers the nets more faster.
                self.dic_cont2domain = {}  #hash: contractor to domain clock
            Funcs:
        '''
        pass

    def parser_feedthrus(self):
        '''
            route -bidir -from gc_spisb_t1 -to gc_spisb_t3 -through { gc_spim_t1 gc_cpf_t gc_iwgr_t gc_utcl2_misc_t gc_utcl2_vml2_t gc_spim_t3 }
        '''
        pass


    def get_portfromdef(self):
        '''
            get port information from def
            - DFTIO_2_Tst_Out0[0] + NET DFTIO_2_Tst_Out0[0] + DIRECTION INPUT + USE SIGNAL
                + LAYER M4 ( 0 0 ) ( 800 80 )
                + FIXED ( 704404 -676840 ) N ;
        '''
        pass

class get_portfromdef(fileparser):
    def __init__(self,file,shape,only_function_port = True,dic_metal_dir = {'M4':0,'M6':0,'M8':0,'M5':1,'M7':1,'M9':1,'M11':1,'M10':0}):
        super(get_portfromdef,self).__init__()
        super(get_portfromdef,self).get_portfromdef()
        pt_start = re.compile(r'^PINS')
        pt_end = re.compile(r'^END PINS')
        pt_port = re.compile(r'- (\S+) \+ NET (\S+)')
        pt_layer = re.compile(r'\+ LAYER (M\d+) \( 0 0 \) \( (\d+) (\d+) \)')
        pt_loc = re.compile(r'\+ (FIXED|PLACED) \( (\S+) (\S+) \) (\S+)')
        pt_design = re.compile(r'DESIGN (\S+) ;')
        pt_depth = re.compile(r'(\S+)\s*(\S+)\s+(\S+)')
        #dic_master2depth = defaultdict(dict)
        #with mkdir(file = 'fileparser/user_define_depth.tune',mode = 'r+', type = 'tunes') as f:
        #    for line in f:
        #        mt_depth = pt_depth.search(line)
        #        if mt_depth:
        #            master,x,y = mt_depth.groups()
        #            dic_master2depth[master] = (400-int(x)/2,400-int(y)/2)
                
        with gzopen(file) as f:
            flag = False
            self.dic_port2layer = {}
            self.dic_port2fixed = {}
            self.design = ''
            self.bbox = defaultdict(dict)
            for line in f:
                mt_start = pt_start.search(line)
                mt_end = pt_end.search(line)
                mt_design = pt_design.search(line)
                if mt_design:
                    self.design = mt_design.groups()[0]
                    for i in shape.dic_tile2poly[self.design]:
                        self.bbox[0][i[0]] = ''
                        self.bbox[1][i[1]] = ''
                    #print self.bbox,self.design
                if mt_start:
                    flag = True
                    continue
                if mt_end:
                    flag = False
                    break
                if flag == False: continue
                mt_port = pt_port.search(line)
                mt_layer = pt_layer.search(line)
                mt_loc = pt_loc.search(line)
                if mt_port:
                    port,net  = mt_port.groups()
                    continue
                if only_function_port and 'FE_FEED' in port: continue
                if mt_layer:
                    layer,w,h = mt_layer.groups()
                    self.dic_port2layer[port] = layer
                    continue
                if mt_loc:
                    status,x,y,orient = mt_loc.groups()
                    x, y = int(x), int(y)
                    if dic_metal_dir[layer] == 0:
                        if x in self.bbox[0]:
                            self.dic_port2fixed[port] = (int(x) + 400,int(y) + int(h)/2)
                        else:
                            self.dic_port2fixed[port] = (int(x)  + int(w) -400,int(y) + int(h)/2)
                    else:
                        if y in self.bbox[1]:
                            self.dic_port2fixed[port] = (int(x) + int(w)/2,int(y) + 400)
                        else:
                            self.dic_port2fixed[port] = (int(x) + int(w)/2 ,int(y) + int(h) - 400)
        #print 'PreAssign number of ports:',self.design,len(self.dic_port2fixed)          


class parser_feedthrus(fileparser):
    def __init__(self,file = 'tune/I2FcInsertFeedThruUnique/ManualFeedthru.txt',rpt = 'fileparser/parser_feedthrus.rpt',file1 = 'rpts/OaFcSpecifyFeedThru/ManualFeedthruTopology.json.gz'):
        super(parser_feedthrus,self).__init__()
        super(parser_feedthrus,self).parser_feedthrus()
        RPT = mkdir_open(rpt,username = self.username)
        #RPT = mkdir_open(rpt,username = 'ppjiang')
        mt_note = re.compile(r'#.*')
        mt_from = re.compile(r'from\s+(\S+)')
        mt_to = re.compile(r'to\s+(\S+)')
        mt_through = re.compile(r'through\s+{\s*(.*)}')
        self.dic_mft = {}  # key = (cmd,start,end,0) 0 -- bidir  1 -- value: topo
        self.dic_mftcount = defaultdict(list)
        if os.path.exists(file1):
            os.system('gunzip -c %s > %s' % (file1,'ManualFeedthruTopology.json'+self.username))
            f = open('ManualFeedthruTopology.json'+self.username,'r+')
            self.dic_fromjson = json.load(f)
        else:
            f = open('ManualFeedthruTopology.json'+self.username,'r+')
            self.dic_fromjson = json.load(f)
        with gzopen(file) as f:
            for line in f:
                line = mt_note.sub('',line).strip() #remove note
                if line:
                    tmp = line.split('-')
                    bidir = 0
                    to = ''
                    start = end = through = ''
                    if 'bidir' in line: bidir = 1
                    pt_1 = mt_from.search(line)
                    pt_2 = mt_to.search(line)
                    pt_3 = mt_through.search(line)
                    if pt_1:
                       start = pt_1.groups()[0]
                       if '/' in start: bidir = 0
                    if pt_2:
                       end = pt_2.groups()[0]
                       if '/' in end: bidir = 0
                    if pt_3:
                        through = [i for i in pt_3.groups()[0].split() if i ] #remove dummy space
                        through.insert(0,start)
                        through.append(end)
                    self.dic_mft[(tmp[0],start, end, bidir)] = through
                    if bidir: self.dic_mft[(tmp[0],end ,start, bidir)] = list(reversed(through))
                    self.dic_mftcount[(tmp[0],start, end, bidir)].append(line)
                    if bidir: self.dic_mftcount[(tmp[0] ,end ,start, bidir)].append(line)
            self.dic_startend  = {}
            for key in  self.dic_mft:
                i = 0
                for c in self.dic_mftcount[key]:
                    i += 1
                    print >>RPT,'#',i,c
                print >>RPT, key,self.dic_mft[key] 
                self.dic_startend[key[1:3]] = self.dic_mft[key]
            print >>RPT,len(self.dic_mft),len(self.dic_startend)
            RPT.close()

class parser_feedconn(fileparser):
    def __init__(self,file='rpts/OaFcCHIPReportCollapseConnectivity/feedthru_connectivity.CHIP.rpt.gz', file1 = 'rpts/OaFcCHIPReportInitialNetlistConnectivity/net_connectivity.CHIP.rpt.gz',read_from_pkl = False):
        print 'Starting processing:',file
        super(parser_feedconn,self).__init__()
        super(parser_feedconn,self).parser_feedconn()
        self.pt_net = re.compile(r'^net:(\S+).*#terms')
        self.pt_drivload = re.compile(r'(driv|load|driver):(\S+)\s*net:(\S+)')
        self.pt_drivload2 = re.compile(r'(driver|load):(\S+)')
        self.pt_netstrip = re.compile(r'\(.*\)')
        file_name = 'feed_connectivity_collapse.pkl'
        self.dic_net2feed = defaultdict(list)
        self.dic_net = {}
        if read_from_pkl:
            with mkdir(file_name = file_name, mode = 'rb',type = 'data') as f:
                db = pickle.load(f)
                self.dic_net = db['dic_net']
                self.dic_net2feed = db['dic_net2feed']
        else:
            with gzopen(file1) as f:
                dic_skipnet = {}
                dic_net2load = defaultdict(int)
                print 'Getting fanout nets, which will be skipped in collapse stage!'
                for line in f:
                    mt_net = self.pt_net.search(line)
                    if mt_net:
                        tmp = mt_net.groups()
                    mt_drivload = self.pt_drivload2.search(line)
                    if mt_drivload:
                        t,port = mt_drivload.groups()
                        if t == 'load':
                            dic_net2load[tmp[0]] += 1
            dic_skipnet = {net:'' for net in dic_net2load if dic_net2load[net] > 1}
            files = file.split()
            AXI = [i for i in files if 'feed_connectivity.Axi.rpt' in i]
            dic_axinet = {}
            if AXI:
                files.remove(AXI[0])
                
                with gzopen(AXI[0]) as f:
                    for line in f:
                        mt_net = self.pt_net.search(line)
                        if mt_net:
                            tmp = mt_net.groups()
                            dic_axinet[tmp[0]] = ''
                        mt_drivload = self.pt_drivload.search(line)
                        if mt_drivload:
                            t,port,net = mt_drivload.groups()
                            self.dic_net2feed[tmp[0]].append(port)
                            self.dic_net[net] = [tmp[0]]
            for feedfile in files:
                with gzopen(feedfile) as f:
                    for line in f:
                        mt_net = self.pt_net.search(line)
                        if mt_net:
                            tmp = mt_net.groups()
                        mt_drivload = self.pt_drivload.search(line)
                        if mt_drivload:
                            t,port,net = mt_drivload.groups()
                            self.dic_net[net] = [tmp[0]]
                            if tmp[0] in dic_axinet: continue
                            self.dic_net2feed[tmp[0]].append(port)
                            
            for net in self.dic_net2feed.keys():
                net_strip = self.pt_netstrip.sub('',net)
                if net_strip in dic_skipnet:
                    self.dic_net2feed.pop(net)
                    #self.dic_net.pop(net)
            db = {}
            db['dic_net2feed'] = self.dic_net2feed
            db['dic_net'] = self.dic_net
            with mkdir(file_name = file_name, mode = 'wb',type = 'data') as f:
                pickle.dump(db,f)
        print 'Ending processing:',file

class parser_netconn2(fileparser):
    def __init__(self,file='rpts/OaFcCHIPReportCollapseConnectivity/net_connectivity.CHIP.rpt.gz',rpt = 'fileparser/parser_netconn.rpt', read_from_pkl = False):
        print 'Starting processing:',file
        super(parser_netconn2,self).__init__()
        super(parser_netconn2,self).parser_netconn()
        self.pt_net = re.compile(r'net:(\S+).*type:(\S+).*#instTerms:(\S+)')
        self.pt_drivload = re.compile(r'(driver|load|bidir):(\S+)')
        
        #if filter_fan: following two varibales only store nets with no fanout
        self.dic_net2driv = defaultdict(list)
        self.dic_net2load = defaultdict(list)
        dic_net2port = defaultdict(list)
        ####################################
        RPT = mkdir_open(rpt)
        if 'Collapse' in file :
            file_name = 'net_connectivity_collapse.pkl'
        elif 'Initial' in file:
            file_name = 'net_connectivity_initial.pkl'
        else:
            file_name = 'net_connectivity_analysis.pkl'
        if read_from_pkl:
            with mkdir(file_name = file_name, mode = 'rb',type = 'data') as f:
                db = pickle.load(f)
                self.dic_net2driv= db['dic_net2driv']
                self.dic_net2load= db['dic_net2load']
        else:
            with gzopen(file) as f:
                for line in f:
                    mt_net = self.pt_net.search(line)
                    if mt_net:
                        tmp = mt_net.groups()
                    mt_drivload = self.pt_drivload.search(line)
                    if mt_drivload:
                        
                        t,port = mt_drivload.groups()
                        dic_net2port[tmp[0]].append(port)
            for net in dic_net2port:
                if len(dic_net2port[net]) != 2  :
                    continue
                else:
                    self.dic_net2driv[net] = dic_net2port[net][0:1]
                    self.dic_net2load[net] = dic_net2port[net][1:]
            db = {}
            db['dic_net2load'] = self.dic_net2load
            db['dic_net2driv'] = self.dic_net2driv
            with mkdir(file_name = file_name, mode = 'wb',type = 'data') as f:
                pickle.dump(db,f)
        RPT.close()
        print 'Ending processing:' ,file
    


class parser_netconn(fileparser):
    def __init__(self,file='rpts/OaFcCHIPReportInitialNetlistConnectivity/net_connectivity.CHIP.rpt.gz',rpt = 'fileparser/parser_netconn.rpt', filter_fan = True, read_from_pkl = False):
        super(parser_netconn,self).__init__()
        super(parser_netconn,self).parser_netconn()
        self.pt_net = re.compile(r'net:(\S+).*type:(\S+).*#instTerms:(\S+)')
        self.pt_drivload = re.compile(r'(driver|load):(\S+)')
        #if filter_fan: following two varibales only store nets with no fanout
        self.dic_net2driv = defaultdict(list)
        self.dic_net2load = defaultdict(list)
        ####################################
        self.dic_tile2net_ordered = {} #(driv,load):[net1,net2,...,netN]
        self.dic_tile2net = {}         #(driv,load):[net1,net2,...,netN]
        self.dic_tile2load = {}        #(driv,load):net:load
        self.dic_tile2driv = {}#(driv,load):net:driv
        self.dic_net2attr = {} 
        self.port2net = {}
        self.netswithfan = []
        RPT = mkdir_open(file_name = rpt, mode = 'w')
        whoami = subprocess.Popen('whoami',stdout=subprocess.PIPE).communicate()[0].strip()
        if read_from_pkl:
            with mkdir(file_name = 'net_connectivity.pkl', mode = 'rb',type = 'data',username = whoami) as file:
                db = pickle.load(file)
                self.dic_net2driv= db['dic_net2driv']
                self.dic_net2load= db['dic_net2load']
                self.port2net = db['port2net']
                self.netswithfan = db['netswithfan']
                self.float_number = 0


        else:
            with gzopen(file) as f:
                for line in f:
                    mt_net = self.pt_net.search(line)
                    if mt_net:
                        tmp = mt_net.groups()
                        self.dic_net2attr[tmp[0]] = (tmp[1],tmp[2])
                    mt_drivload = self.pt_drivload.search(line)
                    if mt_drivload:
                        t,port = mt_drivload.groups()
                        if t == 'driver':
                            self.dic_net2driv[tmp[0]].append(port)
                        else:
                            self.dic_net2load[tmp[0]].append(port)
                        self.port2net[port] = tmp[0]
            
            for net in self.dic_net2driv:
                if len(self.dic_net2driv[net]) != 1 or len(self.dic_net2load[net]) != 1:
                    #store nets need to be filtered out
                    self.netswithfan.append(net)
            
            #remove net in dict    
            if filter_fan:#filter net fanin/fanout more than 1
                for net in self.netswithfan:
                    if net in self.dic_net2driv: self.dic_net2driv.pop(net)
                    if net in self.dic_net2load: self.dic_net2load.pop(net)
            db = {}
            db['port2net'] = self.port2net
            db['dic_net2load'] = self.dic_net2load
            db['dic_net2driv'] = self.dic_net2driv
            db['netswithfan'] = self.netswithfan
            with mkdir(file_name = 'net_connectivity.pkl', mode = 'wb',type = 'data') as file:
                pickle.dump(db,file)
        self.find_conn()
        #self.dic_tile2net_ordered, self.dic_tile2net, self.dic_tile2load, self.dic_tile2driv = self.find_conn()
        self.float_number = len([net  for net in  self.dic_net2driv if net not in self.dic_net2load])
        print >>RPT,"Connection Summary:"
        print >>RPT,"There are total %d nets" % len(self.dic_net2attr)
        print >>RPT,"There are total %d fanout nets " % len(self.netswithfan)
        print >>RPT,"There are total %d float nets" % self.float_number
        RPT.close()

    def find_conn(self):
        '''
            find tile connections (driv,load):[net1,net2,...,netN]
        '''
        self.dic_tile2net = defaultdict(list)
        self.dic_tile2net_ordered = defaultdict(list)
        self.dic_tile2load = defaultdict(dict)
        self.dic_tile2driv = defaultdict(dict)
        self.dic_tile2ports = defaultdict(dict)
        for net in self.dic_net2driv:
            if len(self.dic_net2load[net]) > 1: continue
            if len(self.dic_net2load[net]) == 0: 
                continue
            else:
                load = '/'.join(self.dic_net2load[net][0].split('/')[0:-1])
            driv = '/'.join(self.dic_net2driv[net][0].split('/')[0:-1])
            
            
            key = tuple(sorted([driv,load]))
            key_ordered = (driv,load)
            self.dic_tile2net_ordered[key_ordered].append(net)
            #dic_tile2net_ordered[tuple(reversed(list(key)))].append(net)
            self.dic_tile2net[key].append(net)
            self.dic_tile2load[(driv,load)][self.dic_net2load[net][0]]  = net
            self.dic_tile2driv[(driv,load)][self.dic_net2driv[net][0]]  = net
            self.dic_tile2ports[(driv,load)][(self.dic_net2driv[net][0],self.dic_net2load[net][0])] = net
        #return dic_tile2net_ordered, dic_tile2net, dic_tile2load, dic_tile2driv
    
    def classify_groups(self,shape):
        '''
            Classify groups into following groups
                1. reuse -> * || * -> reuse
                2. non reuse -> non reuse
        '''
        print 'Starting classify groups.'
        #1
        self.dic_group2reuse = defaultdict(dict)
        
        #####
        dic_tmp = defaultdict(dict)
        dic_usedgroup = {}
        for group in self.dic_tile2driv:
            driv, load =  group
            if driv in shape.dic_inst2master:
                net = self.dic_tile2driv[group].values()
                if group in dic_tmp[(shape.dic_inst2master.get(driv,driv),shape.dic_inst2master.get(load,load))]:
                    dic_tmp[(shape.dic_inst2master.get(driv,driv),shape.dic_inst2master.get(load,load))][group].extend(net)
                else:
                    dic_tmp[(shape.dic_inst2master.get(driv,driv),shape.dic_inst2master.get(load,load))][group] = net
            elif driv == '' and load in shape.dic_inst2master:   
                net = self.dic_tile2driv[group].values()
                message0 = 'driv:',driv, 'load:',load
                message1 = 'net number:',len(net),'Ex: net name:',net[0]

                print message0
                print message1
        for master in dic_tmp:
            if len(dic_tmp[master]) > 1:
                for group in dic_tmp[master]:
                    bus_num = len(dic_tmp[master][group])
                    driv, load = group
                    new_key = (driv, load, bus_num)
                    self.dic_group2reuse[master][new_key] = dic_tmp[master][group]
                #self.dic_group2reuse[master] = dic_tmp[master]
                dic_usedgroup.update(self.dic_group2reuse[master])
        #2
        self.dic_group2nonreuse = defaultdict(dict)
        self.dic_group2other = defaultdict(dict)
        for group in self.dic_tile2driv:
            driv, load  = group
            if group not in dic_usedgroup:
                if driv in shape.dic_inst2master and load in shape.dic_inst2master:
                    bus_num = len(self.dic_tile2driv[group].values())
                    new_key = (driv, load, bus_num)
                    self.dic_group2nonreuse[group][new_key] = self.dic_tile2driv[group].values()
                else:
                    new_key = (driv, load, 1)
                    self.dic_group2other[group][new_key] = self.dic_tile2driv[group].values()

        with mkdir('fileparser/Classify_groups.rpt') as f:
            f_detail = mkdir_open('fileparser/detail_Classify_groups.rpt')
            print 'Please check Classify_groups rpt!'
            for group in self.dic_group2reuse:
                print >>f, '#reuse',' '.join(group)
                print >>f_detail, '#reuse',' '.join(group)
                for i in self.dic_group2reuse[group]:
                    print >>f, "%s\t%s\t%s" % (i[0], i[1], i[2])
                    print >>f_detail, "%s\t%s\t%s" % (i[0], i[1], i[2])
                    for net in self.dic_group2reuse[group][i]:
                        print >>f_detail, "\t%s" %  net
                print >>f,''
            print >>f,'#####################################'
            for group in self.dic_group2nonreuse:
                print >>f, '#nonresue',' '.join(group)
                for i in self.dic_group2nonreuse[group]:
                    print >>f,  "%s\t%s\t%s" % (i[0], i[1], i[2])
                    print >>f_detail, "%s\t%s\t%s" % (i[0], i[1], i[2])
                    for net in self.dic_group2nonreuse[group][i]:
                        print >>f_detail, "\t%s" %  net
                print >>f,''

            print >>f,'#####################################'
            for group in self.dic_group2other:
                print >>f, '#io_related',' '.join(group)
                for i in self.dic_group2other[group]:
                    print >>f,  "%s\t%s\t%s" % (i[0], i[1], i[2])
                    print >>f_detail, "%s\t%s\t%s" % (i[0], i[1], i[2])
                    for net in self.dic_group2other[group][i]:
                        print >>f_detail, "\t%s" %  net
                print >>f,''
            f_detail.close()
        print 'Ending classify groups.'


    def filter_net(self,driv,load,order = False):
        if order:
            return self.dic_tile2net[(driv,load)]
        else:
            return self.dic_tile2net_ordered[(driv,load)]
        
        
class parser_xml(fileparser):
    def __init__(self,file = 'data/PrepTopData.xml'):
        self.file_name = file
        self.dic_cont2num    = {}  #hash:contractor to constraint
        self.dic_bundle2net  = defaultdict(list)  #hash: bundle to net.
        self.dic_cont2bundle = defaultdict(list)  #hash: contractor to bundle
        self.dic_bundle2num  = {}  #hash: bundle to constraint
        self.dic_net         = {}  #hash: net to None. Just to transvers the nets more faster.
        self.dic_cont2domain = {}  #hash: contractor to domain clock
        self.dic_net2info =  defaultdict(dict) #Include bundle,fgcg,contractor,constraint,domain,sdc_clk.....
        self.dic_master2info = defaultdict(dict) #Include domain list, instance list...
        try: 
          import xml.etree.cElementTree as ET 
        except ImportError: 
          import xml.etree.ElementTree as ET
        super(parser_xml,self).parser_xml()
        try:
            self.tree = ET.parse(self.file_name)
            self.root = self.tree.getroot()
        except Exception, e:
           print "Error: cannot parse xml file:",self.file_name
           sys.exit(1)

        for contractor in  self.root.findall('rep'):
            tmp_dict = {'contract':contractor.get('contract'),'constraint':contractor.get('constraint'),'domain':contractor.get('domain'),'sdc_clk':contractor.get('sdc_clk')}
            for net in contractor.findall('net'):
                self.dic_net2info[net.get('name')] = {'bundle':net.get('bundle'),'fgcg':net.get('fgcg_ctrl')}
                self.dic_net2info[net.get('name')].update(tmp_dict)
        #for no_rep in self.root.findall('no_rep'):
        #    self.dic_net2info[no_rep.get('name')] = {'bundle':no_rep.get('bundle'),'constraint':'None'}

        for flavor in self.root.findall('tile_flavor'):
            master = flavor.get('flavor')
            clock_domains = [i.get('domain') for i in flavor.findall('clock')]
            instance =  [j.get('name') for j in flavor.findall('instance')]
            if len(clock_domains) <= 0: print "Warning: No clock domains for master: %s" % master
            if len(instance) <= 0: print "Warning: No flavor info for master: %s" % master
            self.dic_master2info[master] = {'instance':instance,'clock_domains': clock_domains}


class analyze_conn(object):
    '''
        TileA -----500 nets ----> TileB
                    |__bundle1
                    |
                    |__bundle2

              -----300 nets ----> TileC
              ......
        Analyze the consistence of every bus
    '''
    def __init__(self, filter = 'io_t' ):
        self.net_conn = parser_netconn()
        self.xml = parser_xml()

        self.shape = getshape.getshape()
        self.shape.parsedef()
        self.shape.getReuse()
        sorted_by_numofnets = sorted(self.net_conn.dic_tile2net.iteritems(),key = lambda x:len(x[1]),reverse = True)
        with open('net_connectivity.rpt','w+') as f:
            
            for master in self.shape.dic_master2inst:
                if  len(self.shape.dic_master2inst[master]) <= 1: continue
                tmp_dict = defaultdict(list)
                tmp_list = []
                print >>f, '#',master
                for i in sorted_by_numofnets:
                    tile_ = list(i[0])
                    instance = list(set(self.shape.dic_master2inst[master]) & set(i[0]))
                    if len(instance) == 1:
                        tile_.remove(instance[0])
                        load =  tile_[0]
                        if load:
                            if load in self.shape.dic_inst2master:
                                tmp_dict[self.shape.dic_inst2master[load]].append((instance[0],load,len(i[1])))
                            else:
                                tmp_dict[load].append((instance[0],load,i[1]))
                        else:
                            tmp_dict['port'].append((instance[0],load,i[1]))
                    elif len(instance) == 2:
                        load = sorted(instance)[1]
                        tmp_dict[self.shape.dic_inst2master[load]].append((sorted(instance)[0],load,len(i[1])))

                for tmp in tmp_dict:
                    print >>f,''
                    #Master,load_master,instance,load_instance,numofnets
                    for tmp2 in sorted(tmp_dict[tmp],key = lambda x:x[2]):
                        print >>f,master,tmp,tmp2
            tmp_dic_notreuse = {master : '' for master in self.shape.dic_master2inst if len(self.shape.dic_master2inst[master]) == 1 }
            tmp_list = []
            for i in sorted_by_numofnets:
                #filter driv and load are not reuse tiles
                driv,load = i[0]
                if filter in driv or filter in load: continue
                if self.shape.dic_inst2master.get(driv,'port') in tmp_dic_notreuse and self.shape.dic_inst2master.get(load,'port') in tmp_dic_notreuse:
                    tmp_list.append((driv, load, len(i[1])))

            for i in sorted(tmp_list,key = itemgetter(0,2)):
                print >>f, i[0],i[1],i,'\n'
                    
                #print >>f,sorted ([i for i in sorted_by_numofnets if set(self.shape.dic_master2inst[master]) & set(i) ])
        
class check_netconn(fileparser):
    def __init__(self,file='rpts/OaFcCHIPReportInitialNetlistConnectivity/net_connectivity.CHIP.rpt.gz',rpt = 'fileparser/check_netconn.rpt'):
        self.shape = getshape.getshape()
        self.shape.parsedef(file="data/Floorplan/*/*.def.gz",read_from_pkl = False)
        self.shape.getReuse()
        self.pt_net = re.compile(r'net:(\S+).*type:(\S+).*#instTerms:(\S+)')
        self.pt_drivload = re.compile(r'(driver|load|bidir):(\S+)')
        #if filter_fan: following two varibales only store nets with no fanout
        self.dic_net2driv = defaultdict(list)
        self.dic_net2load = defaultdict(list)
        RPT = mkdir_open(file_name = rpt, mode = 'w')
        with gzopen(file) as f:
            for line in f:
                mt_net = self.pt_net.search(line)
                if mt_net:
                    tmp = mt_net.groups()
                mt_drivload = self.pt_drivload.search(line)
                if mt_drivload:
                    t,port = mt_drivload.groups()
                    if t == 'driver':
                        self.dic_net2driv[tmp[0]].append(port)
                    else:
                        self.dic_net2load[tmp[0]].append(port)
        self.dic_port2port = defaultdict(dict)
        for net in self.dic_net2driv:
            if len(self.dic_net2driv[net]) == 1 and len(self.dic_net2load[net]) == 1:
                driv = self.dic_net2driv[net][0].split('/',2)
                driv_tile = '/'.join(driv[0:-1])
                if driv_tile not in self.shape.dic_inst2master:continue
                masterdriv = self.shape.dic_inst2master[driv_tile]
                load = self.dic_net2load[net][0].split('/',2)
                load_tile = '/'.join(load[0:-1])
                if load_tile not in self.shape.dic_inst2master:continue
                masterload = self.shape.dic_inst2master[load_tile]
                self.dic_port2port['/'.join([masterdriv,driv[-1]])][masterload] = ''
                #self.dic_port2port['/'.join([masterload,load[-1]])][masterdriv)] = ''
        self.dic_uniq = defaultdict(dict)
        for port in sorted(self.dic_port2port):
            if len(self.dic_port2port[port]) > 1:
                print >>RPT,'#', port
                for p in self.dic_port2port[port]:
                    print >>RPT, p
                print >>RPT, ''
                


            

if __name__ == '__main__':
    #tmp = parser_feedthrus()
    #tmp =  parser_feedconn()
    #tmp = parser_netconn(read_from_pkl = True)
    shape = getshape.getshape()
    shape.parsedef(file="data/Floorplan/*/*.def.gz",read_from_pkl = True)
    shape.getReuse()
    #check_netconn()
    #tmp.classify_groups(shape)
    for file in ["xinlin12/tcls/pindef/*"]:
        print file
        for i in glob.glob(file):
            print i
            tmp = get_portfromdef(file = i,shape = shape)
    #print tmp.design
    #analyze_conn()

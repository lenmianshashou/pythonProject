'''
     Contact: Pengpeng Jiang, 03A312 (Shanghai - Derek Cheng), EXT
     Date: 02/28/2018
     Version:0.22
'''


import getshape,copy
from fileparser import *
from collections import defaultdict
from  mkdir import *
import datetime
import glob
from getParams import *

from create_csh_pre import *
class prepinassign(object):
    def __init__(self):
        self.params = getParams(params = '/home/xinlin12/CAD_regression/pinassign_navi31_vcnbase_unique.cfg')
        self.info = self.params.jsonconf['preassign']
        self.mft = parser_feedthrus(file= self.info["MFTFILE"] )

        self.conn = parser_netconn(file=self.info["NETCONN"],filter_fan = False,read_from_pkl = self.info["NETCONN_READ_FROM_PKL"])
        self.analysis_net()
        self.shape = getshape.getshape()
        self.shape.parsedef(file=self.info["DEF"],read_from_pkl = self.info["DEF_READ_FROM_PKL"],chipname = str(self.info["CHIPNAME"]))
        self.shape.getReuse()
        self.shape.getabuttile()
        self.shape.sortabutlistbycommonedge()
        self.readbkg = getshape.get_blockage(self.shape,tune = self.info["BKG"])
        self.username =  os.popen("who | cut -d' ' -f1 | sort | uniq").readlines()[0].strip()

    def mkdir(self,rpt):
        rpt = '/'.join([self.username , rpt])
        dir = '/'.join(rpt.split('/')[0:-1])
        if os.path.exists(dir):
            pass  
        else :
            os.makedirs(dir)
    
        tmp = open(rpt,'w+')
        return tmp

    def analysis_net(self):
        self.dic_net2load = {}
        self.dic_path2net = defaultdict(int)
        dic_net2others = defaultdict(list)
        for net in self.conn.dic_net2driv:
            start,end = self.conn.dic_net2driv[net],self.conn.dic_net2load[net]
            if len(start)!= 1  or len(end) != 1:
            #filter fanout net
                dic_net2others[net].append(net)
                continue
            start_tile = '/'.join(start[0].split('/')[0:-1])
            end_tile   = '/'.join(end[0].split('/')[0:-1])
            self.dic_path2net[(start_tile, end_tile)] += 1
    def placepin(self):
        placepin_rpt = mkdir_open('prepinassign/prepinassign_placepin.rpt')
        print >>placepin_rpt,'Error01, Error02'
        self.dic_edge2pin_1 = defaultdict(dict)
        dic_tilenotabutlist = defaultdict(list)  #dict store abut tiles by mft but not by script
        dic_specifynet = {}  #dict store nets specified by mft
        self.group_mft = {}
        self.group_others = {}
        self.ports_random = copy.deepcopy(self.conn.port2net)
        #0: Pre process abut tiles
        self.abut_ports = 0 #Store nunmber abut ports
        self.abut_nets  = 0
        self.dic_mft2number = defaultdict(dict)
        for net in self.mft.dic_fromjson['nets']:
            dic_data = self.mft.dic_fromjson['nets'][net][0]
            driverInst = dic_data['driverInst']
            loadInst = dic_data['loadInst']
            topo = [driverInst] + dic_data['thruInsts'] + [loadInst]
            if driverInst not in self.shape.dic_inst2master or loadInst not in self.shape.dic_inst2master or len(self.conn.dic_net2driv.get(net,[])) < 1 or len(self.conn.dic_net2load.get(net,[])) < 1:
                continue
            self.dic_mft2number[(driverInst,loadInst)][tuple(topo)] = ''
            driver = self.conn.dic_net2driv[net][0]
            load = self.conn.dic_net2load[net][0]
            dic_specifynet[net] = ''
            tileabutstart = topo[1]
            tileabutend = topo[-2]
            if tileabutstart in self.shape.dic_inst2master:
                tmp =  [abut[0] for abut in self.shape.dic_tiles[driverInst].abut_inst if abut[2] == tileabutstart]
            else:
                continue
            if tmp:
                if tmp[0] in self.dic_edge2pin_1[driverInst]:
                    self.dic_edge2pin_1[driverInst][tmp[0]].update({driver:''})
                else:
                    self.dic_edge2pin_1[driverInst][tmp[0]] = {driver:''}
                if self.conn.dic_net2driv[net][0] in self.ports_random: 
                    self.ports_random.pop(driver)
            else:
                dic_tilenotabutlist[tuple(sorted([driverInst,tileabutstart]))] .append(topo)
            
            if tileabutend in self.shape.dic_inst2master:
                tmp =  [abut[0] for abut in self.shape.dic_tiles[loadInst].abut_inst if abut[2] == tileabutend]
            else:
                continue
            if tmp:
                if tmp[0] in self.dic_edge2pin_1[loadInst]:
                    self.dic_edge2pin_1[loadInst][tmp[0]].update({load:''})
                else:
                    self.dic_edge2pin_1[loadInst][tmp[0]] = {load:''}
                
                if self.conn.dic_net2load[net][0] in self.ports_random: 
                    self.ports_random.pop(load)
            else:
                dic_tilenotabutlist[tuple(sorted([tileabutend,loadInst]))].append(topo)



        for group in dic_tilenotabutlist:
            print >>placepin_rpt,'Error02:Following group not abutted:', group,len(dic_tilenotabutlist[group])
            print >>placepin_rpt,dic_tilenotabutlist[group][0]
            print >>placepin_rpt
        for group in self.conn.dic_tile2net_ordered:
            if group not in self.group_mft:
                self.group_others[group] = len(self.conn.dic_tile2net_ordered[group])
        placepin_rpt.close()
    def report_pin_density(self,rpt = 'prepinassign/prepinassign_pin_density.rpt'):
        
        self.group2number = defaultdict(int)

        #######
        self.group2func_group = defaultdict(list)
        self.group2feed_group = defaultdict(list)
        for group in self.dic_path2net:
            dic_mft = self.dic_mft2number[group]
            split = 0
            number = self.dic_path2net[group]
            Group = tuple(sorted(group))
            for i in dic_mft:
                if dic_mft[i] == 1: number -= 1
                if dic_mft[i] == '': split += 1
            if self.dic_mft2number[group] == {}:
                self.group2number[Group] += self.dic_path2net[group]
                self.group2func_group[Group].append((self.dic_path2net[group],group))
            else:
                for mft in dic_mft:
                    if dic_mft[mft] == 1:
                        Number = 1
                    else:
                        Number = number/split
                    for num in range(len(mft) - 1):
                        if mft[num] in self.shape.dic_inst2master and mft[num+1] in self.shape.dic_inst2master:
                            group_sub = mft[num:num+2]
                            Group_sub = tuple(sorted(group_sub))
                        else:
                            continue
                        if num == 0: 
                            self.group2number[Group_sub] += Number
                            self.group2func_group[Group_sub].append((Number,group))
                        elif num == len(mft) - 2:
                            self.group2number[Group_sub] += Number
                            self.group2func_group[Group_sub].append((Number,group))
                        else:
                            self.group2number[Group_sub] += int(Number/0.93)
                            self.group2feed_group[Group_sub].append((Number,group))
                        
        with mkdir(rpt) as f:
            self.dic_group2vio = defaultdict(int)
            self.dic_group2vio_single = defaultdict(int)
            self.dic_group2edge = defaultdict(list)
            self.dic_group2info = {}
            dic_pitch = {1:304,0:320}
            dic_dir = {1:'hori',0:'vert'}
            for group in self.group2number :
                tile0, tile1 = group
                if tile0 not in self.shape.dic_inst2master or tile1 not in self.shape.dic_inst2master:
                    continue
                
                    
                abuts = [abut for abut in self.shape.dic_tiles[tile0].abut_inst if abut[2] == tile1]
                length = 0
                tracks = 0
                tracks_single = 0
                if abuts:
                    for abut in abuts:
                        length += abs(abut[-1][-1] - abut[-1][-2])
                        tracks += length/dic_pitch[abut[-1][0]]*3
                        tracks_single += length/dic_pitch[abut[-1][0]]*4
                self.dic_group2edge[group] = abuts
                self.dic_group2info[group] = (length,tracks)
                self.dic_group2vio[group] = tracks - self.group2number[group]
                self.dic_group2vio_single[group] = tracks_single - self.group2number[group] 
            for item in sorted(self.dic_group2vio.items(),key = lambda x : x[1]):
                group = item[0]
                length = float(self.dic_group2info[group][0])/2000
                feed = self.group2number[group]
                #print 'tt',feed,group
                length_slack = length - float((feed/3 + 1)*312)/2000 
                length_slack_single = length - float((feed/4 + 1)*312)/2000
                feed_slack = self.dic_group2vio[group]
                feed_slack_single = self.dic_group2vio_single[group]
                print >>f,'#Group:',item[0], 'Ports_pairs:',feed, 'Overflow:',feed_slack,'Overflow_singlepitch:',feed_slack_single,'Current_length:',length, 'Length_slack:', length_slack,'Length_slack_singlepitch:', length_slack_single
                print >>f,'#Excel:',item[0][0],item[0][1],feed,feed_slack,feed_slack_single,length,length_slack,length_slack_single
                for v in sorted(self.group2func_group[group],key = lambda x: x[0],reverse = True):
                    print >>f,'Func:',v[1],v[0]
                for v in sorted(self.group2feed_group[group],key = lambda x: x[0],reverse = True):
                    print >>f,'Feed:',v[1],v[0],'Collapse ratio:',int(v[0]/0.93)

                    
    def report_pin_misalign(self,rpt01 = 'prepinassign/prepinassign_pin_misalign.rpt',rpt02 = 'prepinassign/prepinassign_pin_misalign_simple.rpt'):
        '''
            Generate a report, port could not be aligned due to conectivity confict or mft
        '''
        RPT = mkdir_open(rpt01)
        RPT01 = mkdir_open(rpt02)
        print >>RPT,'%-16s %-16s %-35s %-5s %-45s %-45s' % ('master','tile','port','side','driv','load')
        print >>RPT01,'%-16s %-16s %-35s %-5s %-45s %-45s' % ('master','tile','port','side','driv','load')
        self.dic_master2port = defaultdict(dict)
        self.dic_tile2portside = defaultdict(dict)
        self.dic_tile2portsimple = defaultdict(dict)
        for tile in self.dic_tile2edge2port:
            master = self.shape.dic_inst2master[tile]
            for edge in self.dic_tile2edge2port[tile]:
                side = self.shape.dic_master2edgeside[master][edge]
                for port in self.dic_tile2edge2port[tile][edge]:
                    self.dic_tile2portside[tile][port] = side
                    if master in self.dic_master2port and port in self.dic_master2port[master]:
                        self.dic_master2port[master][port].add(side)
                    else:
                        self.dic_master2port[master][port] = set([side])
        pt = re.compile(r'\[\d+\]')
        dic_master2number = {}
        dic_master2number2 = defaultdict(int)
        dic_master2simple = {}
        for master in self.dic_master2port:
            dic_simple = defaultdict(dict)
            dic_number = defaultdict(int)
            for port in sorted(self.dic_master2port[master]):
                if len(self.dic_master2port[master][port]) == 1:
                    continue
                instances = self.shape.dic_master2inst[master]
                print >>RPT,''
                port_simple = pt.sub('[*]',port)
                for tile in instances:
                    portinst = '/'.join([tile,port])
                    if portinst in self.conn.port2net:
                        net = self.conn.port2net[portinst]
                        driv = load = '--'
                        if self.conn.dic_net2driv[net]: driv = self.conn.dic_net2driv[net][0]
                        if self.conn.dic_net2load[net]: load = self.conn.dic_net2load[net][0]
                        print >>RPT,'%-16s %-16s %-35s %-5s %-45s %-45s' % (master,tile,port,self.dic_tile2portside[tile].get(port,'--'),driv,load)
                    else:
                        print >>RPT,'%-16s %-16s %-35s %-5s %-45s %-45s' % (master,tile,port,self.dic_tile2portside[tile].get(port,'--'),'--','--')
                    if port_simple in self.dic_tile2portsimple[master]:
                        dic_number[port_simple] += 1
                        dic_master2number2[master] += 1
                        continue

                    else:
                        driv_simple =  pt.sub('[*]',driv)
                        load_simple =  pt.sub('[*]',load)
                        key = '%-16s %-16s %-35s %-5s %-45s %-45s' % (master,tile,port_simple,self.dic_tile2portside[tile].get(port,'--'),driv_simple,load_simple)
                        dic_simple[port_simple][key] = (master,tile,port_simple,self.dic_tile2portside[tile].get(port,'--'),driv_simple,load_simple)
                        dic_number[port_simple] += 1
                        dic_master2number2[master] += 1
                    ######
                    
                
                self.dic_tile2portsimple[master][port_simple] = ''
            dic_master2simple[master] = dic_simple
            dic_master2number[master] = dic_number
        id = 0
        for master in sorted(dic_master2number2.items(),key =lambda x: x[1]):
            dic_simple = dic_master2simple[master[0]]
            dic_number = dic_master2number[master[0]]
            for port_simple in dic_simple:
                for key in dic_simple[port_simple]:
                    print >>RPT01, id, dic_number[port_simple]/len(dic_simple[port_simple]),key
                id += 1
                print >>RPT01,''
        RPT.close()
        RPT01.close()

    def pin_report(self,rpt = 'prepinassign/prepinassign_pin_report.rpt'):
        RPT = mkdir_open(rpt)
        print >>RPT, 'There are %d ports in design;' %  len(self.conn.port2net)
        numofport = 0
        for tile in self.shape.dic_inst2master:
            for edge in self.dic_edge2pin_1[tile]:
                numofport += len(self.dic_edge2pin_1[tile][edge])
        print >>RPT,"There are total %d nets between tiles" % (self.abut_ports)
        print >>RPT,"There are total %d fanout nets " % (len(self.conn.netswithfan),)
        print >>RPT,"There are total %d float nets" % (self.conn.float_number,)
        print >>RPT,'There are %d ports specified by MFT' % (numofport,)
        print >>RPT, 'Following ports are specified mft:'
        for master in self.shape.dic_master2inst:
            instances = self.shape.dic_master2inst[master]
            num = (len(instances) + 1)
            for master_edge in self.shape.dic_ref2inst[instances[0]]:
                print >>RPT,'#Master tile:', master, 'master_edge:', master_edge
                string = (master,) + tuple(instances)
                print >>RPT,'%-50s'* num % string
                string =  (master_edge,) + tuple((self.shape.dic_ref2inst[i][master_edge] for i in instances))
                print >>RPT,'%-50s'* num % string
                for collapse_port in self.dic_mastertile2edge2port[master].get(master_edge,{}):
                    #print self.dic_tile2edge2port[instances[0]].get(master_edge,{}).get(collapse_port,'NO PORT')
                    tmp = [self.dic_tile2edge2port[tile].get(master_edge,{}).get(collapse_port,tile) for tile in instances]
                    tmp.insert(0,collapse_port)
                    tmp = tuple(tmp)
                    print >>RPT,'%-50s' * num  % tmp
        num = 0
        for group in sorted(self.group_mft.items(),key = lambda x:x[1],reverse = True):
            num  += group[1]
            print >>RPT, 'MFT specify',num, group
        for group in sorted(self.group_others.items(),key = lambda x:x[1],reverse = True):
            num  += group[1]
            if group[0][1] in self.shape.dic_inst2master and group[0][0] in self.shape.dic_inst2master:
                if [abut[2] for abut in self.shape.dic_tiles[group[0][0]].abut_inst if abut[2] == group[0][1]]:
                    print >>RPT, 'Abut',num,group
            else:       
                print >>RPT, 'Not Abut',num,group

        RPT.close()
        
    def placemasterpin(self):
        placemasterpin = mkdir_open('prepinassign/prepinassign_placemasterpin.rpt')
        self.portnumber = 0

        #PLace random assign ports:
        self.buffer_pin = {}
        self.dic_master2randomport = defaultdict(dict)
        for port in self.ports_random:
            tile = port.split('/',1)[0]
            if tile not in self.shape.dic_inst2master:  
                self.buffer_pin[port] = ''
                continue
            master = self.shape.dic_inst2master[tile]
            self.dic_master2randomport[master][port] = ''

        dic_tile2edge2port = defaultdict(dict)
        #The variable is used for proc pin_report 
        self.dic_tile2edge2port = defaultdict(dict)
        self.dic_mastertile2edge2port = defaultdict(dict)
        
        ###
        self.dic_master2edgeport = defaultdict(dict)
        for master in self.shape.dic_master2inst:
            tiles = self.shape.dic_master2inst[master]
            for tile in tiles:
                #print tile
                #print self.dic_edge2pin_1[tile].keys()
                for edge in self.dic_edge2pin_1[tile]:
                    #print self.shape.dic_inst2ref[tile].keys()
                    master_edge = self.shape.dic_inst2ref[tile][edge]
                    dic_tile2edge2port[tile][master_edge] = set([port.split('/')[-1] for port in self.dic_edge2pin_1[tile][edge].keys()  ])
                    tmp_dict = {}
                    for port in self.dic_edge2pin_1[tile][edge]:
                         
                        collapse_port = port.split('/')[-1]
                        unique_port = port
                        tmp_dict[collapse_port] = unique_port
                    self.dic_tile2edge2port[tile][master_edge] = tmp_dict
                    if master_edge not in self.dic_mastertile2edge2port[master]:
                        self.dic_mastertile2edge2port[master][master_edge] = copy.deepcopy(tmp_dict)
                    else:
                        self.dic_mastertile2edge2port[master][master_edge].update(tmp_dict)
            res = set()
            dic_edge2port = defaultdict(dict)
            #find master tile's edge
            dic_masteredge2port = defaultdict(dict)
            ports_used = {}
            master_edge = self.shape.dic_ref2inst[tiles[0]].keys()
            for edge in master_edge:
                tmp = []
                for tile in tiles:
                    tile_edge = self.shape.dic_ref2inst[tile][edge]
                    if edge in dic_tile2edge2port[tile]:
                        tmp.append( dic_tile2edge2port[tile][edge])
                    else:
                        tmp.append(set())
                intersection = set() 
                for i in range(len(tmp)):
                    intersection = tmp[i].intersection(tmp[(i+1)%len(tmp)])
                for port in intersection:
                    dic_masteredge2port[edge][port] = ''
                    ports_used[port] = ''
                for tile in tiles:
                    print >>placemasterpin,"Inst:%10s, Master:%10s" %(tile, master)
                    dic_edge2port[tile][edge] = dic_tile2edge2port[tile].get(edge,set()).difference(intersection)
                    for port in dic_edge2port[tile][edge]:
                        if port not in ports_used:
                            dic_masteredge2port[edge][port] = ''
                            ports_used[port] = ''
                    tile_edge = self.shape.dic_ref2inst[tile][edge]
                    print >>placemasterpin,"Edge: ",edge,tile_edge
                    print >>placemasterpin, dic_edge2port[tile][edge]
            
            self.dic_master2edgeport[master] = dic_masteredge2port
        placemasterpin.close()
        self.write_tcl()
        
    def write_tcl(self):
        dic_layer_h = {0:'M5',1:'M7',2:'M9'}
        dic_layer_v = {0:'M4',1:'M6',2:'M8'}
        for master in self.shape.dic_master2inst:
            file_name = 'prepinassign/%s.tcl' % master
            with mkdir(file_name,type = 'data') as f:
                for edge in self.dic_master2edgeport[master]:
                    num = 0
                    for port in self.dic_master2edgeport[master][edge]:
                        print >>f,'set_individual_pin_constraints -side %s -ports [get_ports %s]' % (self.shape.dic_master2edgeside[master][edge],port)
                        #if edge[0] == edge[2]: #vertical
                        #    print >>f,'set_individual_pin_constraints -location {%.3f %.3f} -ports [get_ports %s] -allowed_layers %s' %(float(edge[0])/2000,float(edge[1] + edge[3])/2/2000, port, dic_layer_v[num%3])
                        #else:
                        #    print >>f,'set_individual_pin_constraints -location {%.3f %.3f} -ports [get_ports %s] -allowed_layers %s' %(float(edge[2] + edge[0])/2/2000,float(edge[1])/2000 ,port, dic_layer_h[num%3])
                        
                    
                        num += 1

    def write_csh(self):
        
        tmp = create_csh(self.shape,nlib_stage='prepinassign')
        tmp.create_ndm(inputdef = 'data/Floorplan',
                            inputverilog = 'data/Floorplan',
                            #source_file = []
                            source_file = ['binshi/tcls/blockage/%s_bkg.tcl']
            )
        tmp.pre_create_pindef(inputdef = 'data/Floorplan',
                            inputverilog = 'data/Floorplan',
                            #source_file = []
                            source_file = ['binshi/tcls/blockage/%s_bkg.tcl']
            )
        tmp.create_pinplace_def(inputdef = 'data/Floorplan',
                            inputverilog = 'data/Floorplan',
                            #source_file = []
                            source_file = ['binshi/tcls/blockage/%s_bkg.tcl','binshi/tcls/pindef/%s.def.gz','binshi/tcls/pindef/%s.pin.def.gz']
            )
        tmp.create_I2tcl(chip_path = 'data/Floorplan')
        os._exit(0)
        print 'done'
if __name__ == '__main__':
    pin = prepinassign()    
    pin.placepin()
    pin.placemasterpin()
    pin.report_pin_density()
    pin.pin_report()
    pin.report_pin_misalign()
    pin.report_pin_density()
    pin.write_csh()


    

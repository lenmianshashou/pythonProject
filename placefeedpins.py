#!/tool/aticad/1.0/platform/RH6/bin/python

'''
     Contact: Pengpeng Jiang, 03A312 (Shanghai - Derek Cheng), EXT
     Date: 02/28/2018
     Maintainer: binshi xguchen seito
     Version:1.20
'''
#########################
from collections import defaultdict
from operator import itemgetter
import os,logging
import cPickle as pickle
import re
import glob
import json
import docopt
import pprint
from optparse import *

#########################
import getshape
from mkdir import *
import fileparser
import logging_amd
from daedalus import *
from getParams import *

#e.g. dic_dir2metal = {0:{0:'M4',1:'M6',2:'M8',10:'M10'},1:{0:'M5',1:'M7',2:'M9',11:'M11'},}
#0 - 'Y', 1 - 'X'
#Tim: change layer for Tahiti
dic_dir2metal = {}
dic_allowlayer = {}
def parseOptions(globals):
    """Parse all program options"""

    parser = OptionParser(description= "Place unique pins")

    parser.add_option("--config",
                      action="store", type="string", dest="config", help="Config file")


    (options, args) = parser.parse_args()

    if not options.config:
        logger.error("--config must be specified")
        sys.exit(1)

    commandLine = ' ' . join(sys.argv)
    if args:
        logger.error("Extra arguments ('%s') found on end of command line" % ' ' . join(args))
        sys.exit(1)
    
    return commandLine, options, args


class Placecollapsepins(object):
    def __init__(self,config):
        
        ##Clock ports path
        #self.params = getParams(params = './scripts/pinassign_tahiti_ca_atp.cfg')
        #self.info = self.params.jsonconf['collapse']
        
        self.info = config.jsonconf['collapse']
        self.clockport = self.info["CLOCKPORT"]
        self.layer_info()
        self.shape = getshape.getshape()
        self.shape.parsedef(file=self.info["DEF"],read_from_pkl = self.info["DEF_READ_FROM_PKL"],pkl_name = 'getshape_collapse.pkl',chipname = str(self.info["CHIPNAME"]),track_valid = eval(self.info['VALIDTRACK']))
        self.shape.getReuse()
        self.shape.getabuttile()
        self.shape.sortabutlistbycommonedge()
        self.shape.filter_edge()
        self.readbkg = getshape.get_blockage(self.shape,tune = self.info["BKG"])
        self.get_side()
        self.feedconn = fileparser.parser_feedconn(file=self.info["FEEDCONN"],file1=self.info["INITCONN"],read_from_pkl = self.info["FEEDCONN_READ_FROM_PKL"])
        self.netconn = fileparser.parser_netconn2(file=self.info["NETCONN"],read_from_pkl = self.info["NETCONN_READ_FROM_PKL"])
        self.gen = Portgenerator(self.shape,chipname = str(self.info["CHIPNAME"]),dic_metal_dir = self.dic_metal_dir)
        self.gen.generatepoints()
        #pre assign ports
        self.predef = defpin(files = self.info["PREASSIGN_DEF"].split(),shape = self.shape,gen = self.gen,netconn = self.netconn,dic_metal = self.dic_metal,dic_metal_dir = self.dic_metal_dir)
        self.gen.pre_block_track(dic_group_preassign = self.predef.dic_group_preassign,dic_allowlayer = self.dic_allowlayer)
        self.gen.link_point(self.predef.dic_mastertile2location)
        #get reuse tile list
        self.dic_reuse = {}
        for master in self.shape.dic_master2inst:
            if len(self.shape.dic_master2inst[master]) > 1:
                for tile in self.shape.dic_master2inst[master]:
                    self.dic_reuse[tile] = ''

        #self.dic_feed2portloc = defaultdict(dict) # store topo:net:port location information  
        #self.dic_abut2portloc = defaultdict(dict) # store topo:net:port location information
        self.log = logging_amd.logging_amd(file_name = 'placecollapsepins.log')
        #
        tile = self.shape.dic_inst2master.keys()[0]
        self.pitch = self.gen.dic_edge2pitch

        with mkdir(file_name = 'topo.pkl', mode = 'rb',type = 'data') as file:
            self.dic_topo = pickle.load(file)
            self.fakeabut = defaultdict(list)
            self.dic_mastertile2location = self.predef.dic_mastertile2location
        self.dic_mastertile2constraintlocation = defaultdict(dict)
        with mkdir(file_name = 'relation.pkl', mode = 'rb',type = 'data') as file:
            dic_relation = pickle.load(file)
            self.dic_abutgroup2topo= dic_relation['dic_abutgroup2topo'] 

    def layer_info(self):
        '''
            Get layer information
        '''
        VALIDTRACK = eval(self.info['VALIDTRACK'])
        LAYERINDEX = eval(self.info['LAYERINDEX'])
        self.dic_metal = {}  #layer -> index
        self.dic_metal_dir = {} #Layer -> 'track X|Y', reverse of validtrack dictionary
        self.dic_width = eval(self.info['PINWIDTH'])
        global dic_dir2metal
        self.dic_allowlayer = eval(self.info['ALLOWLAYER'])
        self.dic_allowlayer[0] = len(self.dic_allowlayer['Y'])
        self.dic_allowlayer[1] = len(self.dic_allowlayer['X'])
        track = {'X':1,'Y':0}
        for direction in VALIDTRACK:
            tmp = {}
            for layer in VALIDTRACK[direction]:
                
                if layer in LAYERINDEX:     
                    tmp[LAYERINDEX[layer]] = layer
                    self.dic_metal[layer] = LAYERINDEX[layer]
                self.dic_metal_dir[layer] = track[direction]
            ######Setting golden track info
            self.dic_metal_dir[track[direction]] = VALIDTRACK[direction][0]
            dic_dir2metal[track[direction]] = tmp

    def get_pinname(self):
        '''
            instance pin name -> master pin name
            master pin name -> number of pins connected to it
        '''
        chipname = str(self.info["CHIPNAME"])
        self.dic_inst2masterpin = {}
        self.dic_pin2inst = {}
        self.dic_masterpin2num = {}
        dic_masterpin2num_tmp = defaultdict(dict)
        for net in self.netconn.dic_net2driv:
            driver = self.netconn.dic_net2driv[net][0]
            load = self.netconn.dic_net2load[net][0]
            driv_tile_tmp = self.netconn.dic_net2driv[net][0].split('/',2)
            load_tile_tmp = self.netconn.dic_net2load[net][0].split('/',2)
            driv_tile = '/'.join(driv_tile_tmp[0:-1])
            load_tile = '/'.join(load_tile_tmp[0:-1])
            if '/' not in driver:
                driver_master = chipname
                driv_tile = chipname
                driver = '/'.join([chipname,driver])
                self.netconn.dic_net2driv[net][0] = driver

            else:
                driver_master = self.shape.dic_inst2master.get(driv_tile,driv_tile)
            driver_masterpin = '/'.join([driver_master,driv_tile_tmp[-1]])
            self.dic_inst2masterpin[driver] = driver_masterpin
            self.dic_pin2inst[driver] = driv_tile
            if '/' not in load:
                load_master = chipname
                load_tile = chipname
                load = '/'.join([chipname,load])
                self.netconn.dic_net2load[net][0] =  load
            else:
                load_master = self.shape.dic_inst2master.get(load_tile,load_tile)
            load_masterpin = '/'.join([load_master,load_tile_tmp[-1]])
            self.dic_inst2masterpin[load] = load_masterpin
            self.dic_pin2inst[load] = load_tile
            dic_masterpin2num_tmp[driver_masterpin][load_masterpin] = load_master
            dic_masterpin2num_tmp[load_masterpin][driver_masterpin] = driver_master

        for masterpin in dic_masterpin2num_tmp:
            set0 = set(dic_masterpin2num_tmp[masterpin].keys())
            set1 = set(dic_masterpin2num_tmp[masterpin].values())
            self.dic_masterpin2num[masterpin] = len(set0) - len(set1) + 1

    def classify_ports(self):
        '''
            Classify ports into following categories:
                1. abutting ports
                2. feed ports(not including abutting ports)
                3. float, buffer related,... ports
        '''
        logging.info('Starting classify ports...')
        self.dic_abuttingports = defaultdict(dict)
        self.dic_feedports = defaultdict(dict)
        self.dic_bufferports = defaultdict(dict)
        self.dic_floatports = defaultdict(dict)
        self.dic_fanoutports = defaultdict(dict)
        dic_topo2index = defaultdict(int)
        self.get_pinname()
        chipname = str(self.info["CHIPNAME"])
        for net in self.netconn.dic_net2driv:
            if net not in self.feedconn.dic_net:
                driver = self.netconn.dic_net2driv[net][0]
                load = self.netconn.dic_net2load[net][0]
                if '/' not in driver:
                    self.netconn.dic_net2driv[net][0] = '/'.join([chipname,driver])
                    driver = self.netconn.dic_net2driv[net][0]
                if '/' not in load:
                    self.netconn.dic_net2driv[net][0] =  '/'.join([chipname,load])
                    load = self.netconn.dic_net2load[net][0]

                if len(self.netconn.dic_net2load[net]) == 1:
                    driv_tile = self.dic_pin2inst[driver]
                    load_tile = self.dic_pin2inst[load]
                    if driv_tile in self.shape.dic_inst2master and load_tile in self.shape.dic_inst2master:
                        self.dic_abuttingports[(driv_tile,load_tile)][net] = [driver,load]  
                    elif  driv_tile not in self.shape.dic_inst2master and load_tile not in self.shape.dic_inst2master:
                        continue
                    elif driv_tile not in self.shape.dic_inst2master:
                        if '/' not in driver:
                            self.dic_abuttingports[(chipname,load_tile)][net] = ['/'.join([chipname,driver]),load]
                        else:
                            self.dic_bufferports[(driver,load_tile)][net] =  [driver,load]
                    elif load_tile not in self.shape.dic_inst2master:
                        if '/' not in load:
                            self.dic_abuttingports[(driv_tile,chipname)][net] = [driver,'/'.join([chipname,load])]
                        else:
                            self.dic_bufferports[(driv_tile,load)][net] = [driver,load]
                elif len(self.netconn.dic_net2load[net]) == 0:
                    #driv_tile = self.netconn.dic_net2driv[net][0].split('/',1)[0]
                    driv_tile = '/'.join(driver.split('/',2)[0:-1])
                    self.dic_floatports[(driv_tile,)] = [driver]
                elif len(self.netconn.dic_net2load[net]) > 1:
                    #driv_tile = self.netconn.dic_net2driv[net][0].split('/',1)[0]
                    driv_tile = '/'.join(driver.split('/',2)[0:-1])
                    if driv_tile in self.shape.dic_inst2master:
                        self.dic_fanoutports[(driv_tile,)] = [driver]
                    for port in self.netconn.dic_net2load[net]:
                        #load_tile = port.split('/',1)[0]
                        load_tile = '/'.join(port.split('/',2)[0:-1])
                        if load_tile in self.shape.dic_inst2master:
                            self.dic_fanoutports[(load_tile,)] = [port]
            elif net in self.feedconn.dic_net2feed :
                #if net in feedconn, suppose it belongs to tile -> tile or io_t ->tile
                driver = self.feedconn.dic_net2feed[net][0]
                load = self.feedconn.dic_net2feed[net][-1]
                if '/' not in driver:
                    self.feedconn.dic_net2feed[net][0] = '/'.join([chipname,driver])
                    driver = self.feedconn.dic_net2feed[net][0]
                if '/' not in load:
                    self.feedconn.dic_net2feed[net][-1] = '/'.join([chipname,load])
                    load = self.feedconn.dic_net2feed[net][-1]
                driv_tile = '/'.join(driver.split('/',2)[0:-1])
                load_tile = '/'.join(load.split('/',2)[0:-1])
                if '/' not in driver:
                    self.feedconn.dic_net2feed[net][0] = '/'.join([chipname,driver])
                if '/' not in load:
                    self.feedconn.dic_net2feed[net][-1] = '/'.join([chipname,load])

                if driv_tile in self.shape.dic_inst2master and load_tile in self.shape.dic_inst2master:
                    self.dic_feedports[(driv_tile,load_tile)][net] = self.feedconn.dic_net2feed[net]
                elif driv_tile not in self.shape.dic_inst2master and load_tile not in self.shape.dic_inst2master:
                    self.dic_bufferports[(self.netconn.dic_net2driv[net][0],self.netconn.dic_net2load[net][0])][net] = self.feedconn.dic_net2feed[net]
                    driv_tile =  self.dic_pin2inst[self.feedconn.dic_net2feed[net][2]]
                    load_tile =  self.dic_pin2inst[self.feedconn.dic_net2feed[net][-3]]
                    if len(self.feedconn.dic_net2feed[net]) > 6:
                        self.dic_feedports[(driv_tile,load_tile)][net] = self.feedconn.dic_net2feed[net][2:-2]
                    else:
                        self.dic_abuttingports[(driv_tile,load_tile)][net] = self.feedconn.dic_net2feed[net][2:-2]
                elif driv_tile not in self.shape.dic_inst2master:
                    self.dic_bufferports[(self.netconn.dic_net2driv[net][0],load_tile)][net] = self.feedconn.dic_net2feed[net]
                    driv_tile = self.dic_pin2inst[self.feedconn.dic_net2feed[net][2]]
                    load_tile = self.dic_pin2inst[self.feedconn.dic_net2feed[net][-1]]
                    if len(self.feedconn.dic_net2feed[net]) > 4:
                        self.dic_feedports[(driv_tile,load_tile)][net] = self.feedconn.dic_net2feed[net][2:]
                    else:
                        self.dic_abuttingports[(driv_tile,load_tile)][net] = self.feedconn.dic_net2feed[net][2:]
                elif load_tile not in self.shape.dic_inst2master:
                    self.dic_bufferports[(driv_tile,self.netconn.dic_net2load[net][0])][net] = self.feedconn.dic_net2feed[net]
                    driv_tile = self.dic_pin2inst[self.feedconn.dic_net2feed[net][0]]
                    load_tile = self.dic_pin2inst[self.feedconn.dic_net2feed[net][-3]]
                    if len(self.feedconn.dic_net2feed[net]) > 4:
                        self.dic_feedports[(driv_tile,load_tile)][net] = self.feedconn.dic_net2feed[net][0:-2]
                    else:
                        self.dic_abuttingports[(driv_tile,load_tile)][net] = self.feedconn.dic_net2feed[net][0:-2]
        ##for feed case:
        self.dic_group2topo = defaultdict(dict)
        self.dic_mastergroup2topo = defaultdict(dict)
        self.dic_topo2port = defaultdict(dict)
        self.dic_topo2net = defaultdict(dict)
        for group in self.dic_feedports:
            mastergroup = tuple(self.shape.dic_inst2master[tile] for tile in group)
            for net in self.dic_feedports[group]:   
                startpitch = endpitch = 0
                dic_orient = defaultdict(dict)
                topo = []
                port = []
                for p in self.dic_feedports[group][net]:
                    tmp =  p.split('/')
                    tile_ = '/'.join(tmp[0:-1])
                    if tile_ not in self.shape.dic_inst2master: continue
                    topo.append(tile_)
                    port.append(tmp[-1])
                self.dic_topo2port[tuple(topo)][tuple(port)] = ''
                self.dic_topo2net[tuple(topo)][net] = ''
                self.dic_group2topo[group][tuple(topo)] = ''
                self.dic_mastergroup2topo[mastergroup][tuple(topo)] = ''
            
        self.dic_topo2step = defaultdict(dict)
        self.dic_group2maxstep = defaultdict(int)
        dic_topo2orient = {}
        dic_topo2master = {}
        dic_topo2candidate = {}
        
        for mastergroup in self.dic_mastergroup2topo:
            max_step = 0
             
            for topo in self.dic_mastergroup2topo[mastergroup]:
                
                dic_jump = defaultdict(int)
                dic_master2port = defaultdict(dict)
                mastertopo = [self.shape.dic_inst2master[tile] for tile in topo]
                orienttopo = [self.shape.dic_tiles[tile].inst_orient for tile in topo]
                dic_topo2orient[topo] = tuple(orienttopo)
                dic_topo2master[topo] = tuple(mastertopo)
                start_count = ((mastertopo+ [mastertopo[-1]]).count(mastertopo[0]) - 1)/2 + 1
                end_count = (([mastertopo[0]] +mastertopo).count(mastertopo[-1]) - 1)/2 + 1
                if max((start_count,end_count)) > max_step: max_step = max((start_count,end_count))
                candidate_port = self.dic_topo2port[topo].keys()[0]
                dic_topo2candidate[topo] = candidate_port
                max_collapse = 0
                for i,port in enumerate(candidate_port):
                    masterpin = '/'.join([mastertopo[i],port])
                    if self.dic_masterpin2num.get(masterpin,0) > max_collapse:
                        max_collapse = self.dic_masterpin2num[masterpin] 
                    if topo[i] not in dic_jump:
                        dic_master2port[mastertopo[i]][port] = ''
                        dic_jump[topo[i]] = len(dic_master2port[mastertopo[i]]) - 1
                self.dic_group2maxstep[mastergroup] = max(max(dic_jump.values()) ,max_step, max_collapse)
                self.dic_topo2step[topo] = dic_jump

        with mkdir('placecollapsepins/step_case.tune',type = 'tunes',mode = 'r+') as f:
            '''
                #specify pitch among pins
                Format:
                gc_tcc_3_t gc_ea_t 4
                gc_tcc_0_t gc_ea_t 4
                gc_tcc_2_t gc_ea_t 4
                gc_tcc_1_t gc_ea_t 4
                gc_tcc_2_t gc_ea_0_t 4
                gc_tcc_0_t gc_ea_0_t 4
                gc_tcc_t gc_ea_0_t 4
                gc_tcc_1_t gc_ea_0_t 4
            '''
            for line in f:
                tmp = line.split()
                mastergroup= tmp[0:-1]
                step = int(tmp[-1])
                #self.dic_topo2step[tuple(topo)] = dict(zip(topo,step) )
                #self.dic_topo2step[tuple(reversed(topo))] = dict(zip(reversed(topo),reversed(step)))
                self.dic_group2maxstep[tuple(mastergroup)] = step
                self.dic_group2maxstep[tuple(reversed(mastergroup))] = step

        with mkdir('placecollapsepins/step_case.rpt') as f:
            for mastergroup in self.dic_mastergroup2topo:
                print >>f,'#group:',mastergroup,self.dic_group2maxstep[mastergroup]
                for topo in self.dic_mastergroup2topo[mastergroup]:
                    orient = dic_topo2orient[topo]
                    master = dic_topo2master[topo]
                    print >>f, '#',topo
                    for (i,tile) in enumerate(topo):
                        print >>f,tile,dic_topo2candidate[topo][i]
                    print >>f, '%-15s' * len(topo) % tuple(topo)
                    print >>f, '%-15s' * len(topo) % dic_topo2orient[topo]
                    print >>f, '%-15s' * len(topo) % dic_topo2master[topo]
                    print >>f, '%-15s' * len(topo) % tuple([self.dic_topo2step[topo][i]  for i in topo])
        with mkdir('placecollapsepins/classify_ports_feed.rpt') as f:
            print >>f,'#dic_abuttingports'
            for i in self.dic_abuttingports: print >>f, i
            print >>f,'#dic_feedports'
            for i in  self.dic_feedports: print >>f, i
            print >>f,'#dic_bufferports'
            for i in self.dic_bufferports: print >>f, i
            print >>f,'#dic_floatports'
            for i in self.dic_floatports: print >>f, i
            print >>f,'#dic_fanoutports'
            for i in self.dic_fanoutports: print >>f, i

        logging.info('Ending classify ports.')
        
    def preassignpins(self,auto_fix_preassign_confliction = True):
        '''
            Assign pins connected to pre assigned pins
        '''
        auto_fix_preassign_confliction = self.info["FIX_PREASSIGN_CONFLICTION"]
        with mkdir('placecollapsepins/preassignpins.rpt', mode = 'w') as f:
            dic_pin2abutpin = defaultdict(dict)
            dic_mastertile2location = defaultdict(dict)
            dic_mastertile2locationDrop = defaultdict(dict)
            dic_master2usedtrack = defaultdict(dict)
            #print self.dic_mastertile2location['gc_tcri2_t']['TCC3_TCR_data_out1_data[934]']
            for group in self.dic_abuttingports:
                for net in self.dic_abuttingports[group]:
                    ports = self.dic_abuttingports[group][net]  
                    if ports:
                        dic_pin2abutpin[ports[0]] = [group,ports]
                        dic_pin2abutpin[ports[1]] = [group,ports]
            for group in self.dic_feedports:
                for net in self.dic_feedports[group]:
                    ports = self.dic_feedports[group][net]
                    #below ports[-2] out of range because of net was drive only
                    a,b,c,d = ports[0],ports[1],ports[-2],ports[-1]
                    A,B,C,D = [i.split('/')[0] for i in (a,b,c,d)]
                    dic_pin2abutpin[ports[0]] =  [(A,B),(a,b)]
                    dic_pin2abutpin[ports[1]] =  [(A,B),(a,b)]
                    dic_pin2abutpin[ports[-2]] = [(C,D),(c,d)]
                    dic_pin2abutpin[ports[-1]] = [(C,D),(c,d)]
            for master in self.dic_mastertile2location:
                for port in self.dic_mastertile2location[master]:
                    masterpoint,layer,dir = self.dic_mastertile2location[master][port]
                    dic_master2usedtrack[master][(masterpoint,layer)] = 0
            for master in self.dic_mastertile2location:
                instance = self.shape.dic_master2inst[master]
                for port in self.dic_mastertile2location[master]:
                    for inst in instance:
                        print >>f ,'###test %s %s %s' %(master, inst, port)
                        pin = '/'.join([inst,port])
                        if pin not in dic_pin2abutpin: 
                            print >>f,'check1'
                            continue
                        group,ports = dic_pin2abutpin[pin]
                        id = ports.index(pin)
                        masterpoint,layer,dir = self.dic_mastertile2location[master][port]
                        point = '-!-'
                        if group not in self.gen.dic_group2info:
                            print >>f, 'Error: group',group,'not abutted'
                            continue
                        for d in self.gen.dic_group2info[group].availpoints.keys():
                            if masterpoint in self.gen.dic_group2info[group].group2set_reversed[d][group[id]]:  
                                point = self.gen.dic_group2info[group].group2set_reversed[d][group[id]][masterpoint]
                                break
                        if point == '-!-':
                            print >>f,'check2'
                            continue
                        inst_abut = group[(id+1)%2]
                        master_abut = self.shape.dic_inst2master[inst_abut]
                        port_abut = ports[(id+1)%2].split('/')[-1]
                        masterpoint_abut = self.gen.dic_group2info[group].group2set[d][inst_abut][point]
                        if (masterpoint_abut,layer) in dic_master2usedtrack[master_abut]:
                            continue
                        else:
                            dic_master2usedtrack[master_abut][(masterpoint_abut,layer)] = 0
                        if port_abut not in dic_mastertile2location[master_abut]:
                            dic_mastertile2location[master_abut][port_abut] = (masterpoint_abut,layer,dir)
                        if auto_fix_preassign_confliction:
                            print >>f,master_abut,port_abut
                            if (masterpoint_abut,layer,dir) != dic_mastertile2location[master_abut][port_abut]:
                                dic_mastertile2locationDrop[master][port] = ""
                                print >>f,"Warning: preassign pin conflicted, Drop it"
                        print >>f,'Master: %s instance: %s port: %s %s %s %s' %(master, instance, port, masterpoint,layer,dir)
                        print >>f,"Preassign abutting pins:",group,point,masterpoint_abut,port_abut,'\n'
            for master in dic_mastertile2location:
                self.dic_mastertile2location[master].update(dic_mastertile2location[master])
            for master in dic_mastertile2locationDrop:
                for port in dic_mastertile2locationDrop[master]:
                    self.dic_mastertile2location[master].pop(port)
            #print self.dic_mastertile2location['gc_tcri2_t']['TCC3_TCR_data_out1_data[934]']
        self.gen.link_point(self.dic_mastertile2location)
    def classify_groups(self):
        '''
            Classify groups into following groups
                1. reuse -> * || * -> reuse
                2. non reuse -> non reuse
        '''
        logging.info('Starting classify groups.')
        #1
        self.dic_groupdriv = defaultdict(dict)
        
        #####
        dic_tmp = defaultdict(dict)
        dic_usedgroup = {}
        for group in self.dic_feedports:
            driv, load =  group
            dic_tmp[(self.shape.dic_inst2master[driv],self.shape.dic_inst2master[load])][group] = ''
        
        for group in dic_tmp:
            if len(dic_tmp[group]) > 1:
                self.dic_groupdriv[group] = dic_tmp[group]
                #dic_usedgroup.update(dic_tmp[group])
        #2
        self.dic_groupother = defaultdict(dict)
        for group in self.dic_feedports:
            if group not in dic_usedgroup:
                self.dic_groupother[group][group] = ''
         
        with mkdir('placecollapsepins/Classify_groups.rpt') as f:
            logging.debug('Please check Classify_groups rpt!')
            for group in self.dic_groupdriv:
                print >>f, group
                for i in self.dic_groupdriv[group]:
                    print >>f,i
                print >>f,''
            print >>f,'#####################################'
            for group in self.dic_groupother:
                print >>f, group
                for i in self.dic_groupother[group]:
                    print >>f,i
                print >>f,''
        logging.info('Starting classify groups.')
    
    
        
    def get_abuttingorder(self):
        '''
            Define order of abutting groups
            ex:
            Master group Instance group
            umc_umcch_t umc_umcch_t
            umc_umc_t umc_umcch_t
            umc_umcch_t umc_umc_t
            umc_umc_t umc_umcch_0_t umc_umc_t3 umc_umcch_t31
            umc_umcch_0_t umc_umc_t umc_umcch_t31 umc_umc_t3
            umc_umcch_0_t umc_umcch_0_t
        '''
        self.dic_mastergroup2order = {}
        self.dic_mastergroup2sequence = defaultdict(int)
        sequence  = 0
        with mkdir('placecollapsepins/abut_order.tune',type = 'tunes',mode = 'r+') as f:
            for line in f:
                if '#' in line: continue   
                tmp = line.strip().split()
                mastergroup_r = tuple(reversed(tmp[0:2]))
                mastergroup = tuple(tmp[0:2])
                group = []
                group_r = []
                tmp2 = tmp[2:]
                self.dic_mastergroup2sequence[mastergroup] = sequence
                self.dic_mastergroup2sequence[mastergroup_r] = sequence
                sequence  += 1
                for i in range(len(tmp2)):
                    if i%2 == 0:    
                        group.append(tuple(tmp2[i:i+2]))
                        group_r.append(tuple(reversed(tmp2[i:i+2])))
                self.dic_mastergroup2order[mastergroup] = group
                self.dic_mastergroup2order[mastergroup_r] = group_r
    def get_feedorder(self):
        '''
            Define order of feed groups
            MG:df_cs_t umc_umcch_t
            TOPO:df_cs_t2 umc_umc_t0 umc_umc_t0 umc_umcch_t01 umc_umcch_t01 umc_umcch_t00
        '''
        self.dic_mastergroup2feedorder = defaultdict(list)
        self.dic_mastergroup2feedsequence = defaultdict(int)
        sequence  = 0
        pt_mg = re.compile(r'MG:(.*)')
        pt_topo = re.compile(r'TOPO:(.*)')
        with mkdir('placecollapsepins/feed_order.tune',type = 'tunes',mode = 'r+') as f:
            for line in f:
                if '#' in line: continue
                mt_mg  = pt_mg.search(line)
                mt_topo = pt_topo.search(line)
                if mt_mg:
                    tmp_group = mt_mg.groups()[0].split()
                    mastergroup  = tuple(tmp_group)
                    mastergroup_r  = tuple(reversed(tmp_group))
                    self.dic_mastergroup2feedsequence[mastergroup] = sequence
                    self.dic_mastergroup2feedsequence[mastergroup_r] = sequence
                    sequence  += 1
                if mt_topo:
                    topo = mt_topo.groups()[0].split()
                    self.dic_mastergroup2feedorder[mastergroup].append(tuple(topo))
                    self.dic_mastergroup2feedorder[mastergroup_r].append(tuple(reversed(topo)))
        self.get_prioredge(sequence)

    def get_allow_single(self):
        '''
            Define topo allowing single pitch
            MG:gc_tcc_0_t gc_ea_t
        '''
        self.dic_mastergroupofsingle = {}
        pt_mg = re.compile(r'MG:(.*)')
        pt_topo = re.compile(r'TOPO:(.*)')
        with mkdir('placecollapsepins/allow_single.tune',type = 'tunes',mode = 'r+') as f:
            for line in f:
                if '#' in line: continue
                mt_mg  = pt_mg.search(line)
                mt_topo = pt_topo.search(line)
                if mt_mg:
                    tmp_group = mt_mg.groups()[0].split()
                    mastergroup  = tuple(tmp_group)
                    mastergroup_r  = tuple(reversed(tmp_group))
                    self.dic_mastergroupofsingle[mastergroup] = set()
                    self.dic_mastergroupofsingle[mastergroup_r] = set()

    def align_direction(self):
        '''
           Specify align direction
           Format:MasterA MasterB
        '''
        self.dic_align_direction = {}
        with mkdir('placecollapsepins/align_direction.tune',type = 'tunes',mode = 'r+') as f:
            for line in f:
                if '#' in line: continue
                self.dic_align_direction[tuple(line.split())] = ''

    def get_prioredge(self,sequence):
        '''
            It will try to assign pins of topo with specified edge
            EDGE:gc_tcc_t23 gc_cpc_t
            EDGE:gc_tcc_t23 gc_cpf_t
        '''
        pt_edge = re.compile(r'EDGE:(\S+)\s+(\S+)')
        with mkdir('placecollapsepins/prioredge.tune',type = 'tunes',mode = 'r+') as f:
            for line in f:
                mt_edge =pt_edge.search(line)
                if mt_edge:
                    a,b = mt_edge.groups()
                    for abutgroup in [(a,b),(b,a)]:
                        for topo in  self.dic_abutgroup2topo[abutgroup]:
                            if topo[0] not in self.shape.dic_inst2master or topo[-1] not in self.shape.dic_inst2master:
                                continue
                            mg =  (self.shape.dic_inst2master[topo[0]],self.shape.dic_inst2master[topo[-1]])
                            if mg in self.dic_mastergroup2feedsequence:
                                self.dic_mastergroup2feedorder[mg].append(topo)
                            else:
                                sequence += 1
                                self.dic_mastergroup2feedsequence[mg] = sequence
                                self.dic_mastergroup2feedorder[mg].append(tuple(topo))

    def get_pregroupabut(self):
        self.dic_mastergroup2userabut  = defaultdict(dict)
        with  mkdir('placecollapsepins/group_abut.tune',type = 'tunes',mode = 'r+') as f:
            dic_tmp = defaultdict(dict)
            for line in f:
                tmp = line.split()
                if tmp == []: continue
                mastergroup = (tmp[1],tmp[2])
                instancegroup = []
                for i in range(len(tmp[3:])/2):
                    instancegroup.append(tuple(tmp[3+i*2:(i+1)*2+3]))
                dic_tmp[tmp[0]][mastergroup] = instancegroup

            for gc in dic_tmp:
                for mastergroup in dic_tmp[gc]:
                    self.dic_mastergroup2userabut[mastergroup] = dic_tmp[gc]

    def get_prefeedabutinggroups(self):
        self.prefeedabuttinggroups = []
        with  mkdir('placecollapsepins/prefeedabuttinggroups.tune',type = 'tunes',mode = 'r+') as f:
            for line in f:
                line = line.strip()
                if '#' in line: continue
                if line:   
                    groups = line.split()
                    self.prefeedabuttinggroups.append(tuple(groups))
                    self.prefeedabuttinggroups.append(tuple(reversed(groups)))
        
    def placeabutports(self,specify = False):
        '''
            place abut ports
        '''
        self.get_abuttingorder()
        self.unplacednum = 0
        self.get_pregroupabut()
        self.get_prefeedabutinggroups()
        if specify:
            f = mkdir_open('placecollapsepins/placeabutports.rpt')
        else:
            f = mkdir_open('placecollapsepins/placeabutports.rpt',mode = 'a+')
        self.mastergroup2instgroup = defaultdict(dict)
        for group in self.dic_abuttingports: 
            self.mastergroup2instgroup[tuple([self.shape.dic_inst2master[i] for i in group])][group] = ''
        ###Meger unporcess topo path into abut ports
        for topo in  self.dic_topo['group_unprocess']:
            group = (topo[0],topo[-1])
            for i in range(len(topo)/2):
                mastergroup = tuple(self.shape.dic_inst2master[tile] for tile in topo[i*2:i*2+2])
                self.mastergroup2instgroup[mastergroup][topo[i*2:i*2+2]] = ''
            for net in self.dic_topo2net[topo]:
                for i in range(len(topo)/2):
                    abutgroup = topo[i*2:i*2+2]
                    abutport = self.dic_feedports[group][net][i*2:i*2+2]
                    if len(abutport) != 2:
                        continue
                    self.dic_abuttingports[abutgroup][net] = abutport
    
        for mastergroup in self.fakeabut:
            for topo in self.fakeabut[mastergroup]:
                group = (topo[0],topo[-1])
                for i in range(len(topo)/2):
                    mastergroup = tuple(self.shape.dic_inst2master[tile] for tile in topo[i*2:i*2+2])
                    self.mastergroup2instgroup[mastergroup][topo[i*2:i*2+2]] = ''
                for net in self.dic_topo2net[topo]:
                    for i in range(len(topo)/2):
                        abutgroup = topo[i*2:i*2+2]
                        abutport = self.dic_feedports[group][net][i*2:i*2+2]
                        if len(abutport) != 2:
                            continue
                        self.dic_abuttingports[abutgroup][net] = abutport
        for mastergroup in self.mastergroup2instgroup:
            if mastergroup not in self.dic_mastergroup2sequence:
                self.dic_mastergroup2sequence[mastergroup] = 101
        if specify:
            mastergroups = self.prefeedabuttinggroups
            note = "Pre Feed Abut group:"
        else:
            mastergroups = [i[0] for i in sorted(self.dic_mastergroup2sequence.items(),key =lambda x:x[1])]
            note = "Abut group:"
        for mastergroup in mastergroups:
            print note,mastergroup
            print >>f,note,mastergroup
            if mastergroup == ():
                continue

            inst_groups = defaultdict(int)
            self.tile2availpoint = defaultdict(dict)
            self.master2availpoint = defaultdict(dict)
            self.group2availpoint = defaultdict(list)
            edge_set = set([])
            dic_dir2sortedpoints = defaultdict(dict)
            dic_master2num = defaultdict(int)
            if mastergroup in self.dic_mastergroup2userabut:
                usergroups = {}
                for i in self.dic_mastergroup2userabut[mastergroup]:
                    usergroups.update(self.mastergroup2instgroup[i])
                    for remove_g in self.dic_mastergroup2userabut[mastergroup][i]:
                        if remove_g in usergroups:
                            usergroups.pop(remove_g)
                print >>f,'Groups to find common edge'
                for i in usergroups:        
                    print >>f,usergroups
            else:
                usergroups = self.mastergroup2instgroup[mastergroup]
            for group in usergroups:
                dic_master2num[self.shape.dic_inst2master[group[0]]] += 1
                dic_master2num[self.shape.dic_inst2master[group[1]]] += 1
            for group in usergroups:
                if group[0]  == group[1]:
                    groups_ = [gp for gp in self.gen.dic_group2info if group[0] in gp and group != gp]
                    need = len(self.dic_abuttingports[group])
                    tracks_ = []
                    for g in groups_:
                        Dir = self.gen.dic_group2info[g].max_dir
                        #self.update_abut_avail(Dir,g,g[0])
                        #self.update_abut_avail(Dir,g,g[1])
                        for p in self.gen.dic_group2info[g].availpoints[Dir]:
                            tmp_set = self.gen.dic_group2info[g].availpoints[Dir][p][group[0]] - set([4,3])
                            if len(tmp_set) == 0:
                                tracks_.append([g,Dir,p])
                        need -= 1
                        if need == 0:
                            break
                    master = self.shape.dic_inst2master[group[0]]
                    for net in self.dic_abuttingports[group]:
                        if tracks_: 
                            g,d,p =  tracks_.pop()
                        else:
                            print >>f,'Error: No enough pitch for SN00',port
                            break
                        self.gen.dic_group2info[g].availpoints[d][p][group[0]] |= set([0,1])
                        port = [p_.split('/')[-1] for p_ in self.dic_abuttingports[group][net]]
                        masterpoint = self.gen.dic_group2info[g].group2set[d][group[0]][p]
                        if not port: 
                            print >>f,'SN00:Error,',net
                            continue
                        if port[1] not in self.dic_mastertile2location[master]:
                            self.dic_mastertile2location[master][port[1]] = (masterpoint,1,d)
                            print >>f, 'SN00:Tile: %-15s Port: %-82s %-10s  %-10s %-10s %-10s' %(group[1],port[1],p,masterpoint[0],masterpoint[1],1)
                            
                        if port[0] not in self.dic_mastertile2location[master]:
                            self.dic_mastertile2location[master][port[0]] = (masterpoint,0,d)
                            print >>f, 'SN00:Tile: %-15s Port: %-82s %-10s  %-10s %-10s %-10s' %(group[0],port[0],p,masterpoint[0],masterpoint[1],0)
                    continue
                elif group not in self.gen.dic_group2info: 
                    print >>f,'Error:#group %s skip' % '*'.join(group)
                    self.unplacednum += len(self.dic_abuttingports[group])*2
                    print >>f,'Unplaced port number:',self.unplacednum
                    continue
                for dir in self.gen.dic_group2info[group].availpoints:
                    #self.update_abut_avail(dir,group,group[0])
                    #self.update_abut_avail(dir,group,group[1])
                    dic_dir2sortedpoints[group][dir] = sorted(self.gen.dic_group2info[group].availpoints[dir])
                #create common available points for groups in one mastergroup
                group0_loc = self.gen.dic_group2info[group].group2loc[group[0]]
                group1_loc = self.gen.dic_group2info[group].group2loc[group[1]]
                for edge in  self.gen.dic_group2info[group].availpoints:
                    inst_groups[group] += len(self.gen.dic_group2info[group].availpoints[edge])
                    if group0_loc not in self.tile2availpoint[group[0]]:
                        self.tile2availpoint[group[0]][group0_loc] = []
                    if group1_loc not in self.tile2availpoint[group[1]]:
                        self.tile2availpoint[group[1]][group1_loc] = []
                    self.tile2availpoint[group[0]][group0_loc].append(set(self.gen.dic_group2info[group].group2set_reversed[edge][group[0]]))
                    self.tile2availpoint[group[1]][group1_loc].append(set(self.gen.dic_group2info[group].group2set_reversed[edge][group[1]]))
            for group in inst_groups:
                group0_loc = self.gen.dic_group2info[group].group2loc[group[0]]
                group1_loc = self.gen.dic_group2info[group].group2loc[group[1]]
                self.tile2availpoint[group[0]][group0_loc] = [reduce(lambda x, y: x | y, self.tile2availpoint[group[0]][group0_loc])]
                self.tile2availpoint[group[1]][group1_loc] = [reduce(lambda x, y: x | y, self.tile2availpoint[group[1]][group1_loc])]

            for group in inst_groups:  
                
                group0_loc = self.gen.dic_group2info[group].group2loc[group[0]]
                group1_loc = self.gen.dic_group2info[group].group2loc[group[1]]
                mastergroupTmp =  [self.shape.dic_inst2master[t] for t in group]
                if group0_loc not in self.master2availpoint[mastergroupTmp[0]] or group1_loc not in self.master2availpoint[mastergroupTmp[1]]:
                    self.master2availpoint[mastergroupTmp[0]][group0_loc] = []
                    self.master2availpoint[mastergroupTmp[1]][group1_loc] = []
                self.master2availpoint[mastergroupTmp[0]][group0_loc].append(self.tile2availpoint[group[0]][group0_loc][0])
                self.master2availpoint[mastergroupTmp[1]][group1_loc].append(self.tile2availpoint[group[1]][group1_loc][0])
            
            for group0_loc in self.master2availpoint[mastergroup[0]]:
                self.master2availpoint[mastergroup[0]][group0_loc] = [reduce(lambda x, y: x & y, self.master2availpoint[mastergroup[0]][group0_loc])]   
            for group1_loc in self.master2availpoint[mastergroup[1]]:
                self.master2availpoint[mastergroup[1]][group1_loc] = [reduce(lambda x, y: x & y, self.master2availpoint[mastergroup[1]][group1_loc])]
            #filter group not belong to mastergroup    
            inst_groups = {}
            for group in self.mastergroup2instgroup[mastergroup]:
                if group in self.gen.dic_group2info and group[0]  != group[1]:
                    for edge in  self.gen.dic_group2info[group].availpoints:
                        inst_groups[group] = len(self.gen.dic_group2info[group].availpoints[edge])
            for group in inst_groups:
                group0_loc = self.gen.dic_group2info[group].group2loc[group[0]]
                group1_loc = self.gen.dic_group2info[group].group2loc[group[1]]
                tmp_dict0 = {}
                tmp_dict1 = {}
                for p in self.master2availpoint[mastergroup[0]][group0_loc][0]:
                    if p in self.gen.dic_group2info[group].group2set_reversed[0].get(group[0],{}):
                        tmp_dict0[(0,self.gen.dic_group2info[group].group2set_reversed[0][group[0]][p])] = ''
                    elif p in self.gen.dic_group2info[group].group2set_reversed[1].get(group[0],{}):
                        tmp_dict0[(1,self.gen.dic_group2info[group].group2set_reversed[1][group[0]][p])] = ''

                for p in self.master2availpoint[mastergroup[1]][group1_loc][0]:
                    if p in self.gen.dic_group2info[group].group2set_reversed[0].get(group[1],{}):
                        tmp_dict1[(0,self.gen.dic_group2info[group].group2set_reversed[0][group[1]][p])] = ''
                    elif p in self.gen.dic_group2info[group].group2set_reversed[1].get(group[1],{}):
                        tmp_dict1[(1,self.gen.dic_group2info[group].group2set_reversed[1][group[1]][p])] = ''  
                a = set( tmp_dict0 )
                b = set( tmp_dict1 )
                self.group2availpoint[group].append(a & b - set([edge,0]))
                self.group2availpoint[group] = reduce(lambda x, y: x & y, self.group2availpoint[group])
            # To assign port in shortest abutting edge firstly;
            
           
            inst_groups = [i[0] for i in sorted(inst_groups.items(),key = lambda x:x[1])]
            if mastergroup in self.dic_mastergroup2order:
                First = self.dic_mastergroup2order[mastergroup]
                print >>f,'#User define order old:',First,inst_groups
                first = []
                for i in First:
                    if i in inst_groups:
                        inst_groups.remove(i)
                        first.append(i)
                inst_groups = first + inst_groups
                print >>f,'#User define order new:',first,inst_groups
            for group in inst_groups:
                #for dir in self.gen.dic_group2info[group].availpoints:
                #    self.update_abut_avail(dir,group,group[0])
                #    self.update_abut_avail(dir,group,group[1])
                avail_points = []
                avail_points_uncommon = []
                mastergroup = [self.shape.dic_inst2master[m] for m in group]
                for dir in self.gen.dic_group2info[group].availpoints:
                    #self.update_avail(dir,group,group[0])
                    #self.update_avail(dir,group,group[1])

                    for point in self.gen.dic_group2info[group].availpoints[dir]:
                        tmp_dict = self.gen.dic_group2info[group].availpoints[dir][point]
                        #print 'ccccccc',tmp_dict,point
                        if tmp_dict[group[0]] == set() and tmp_dict[group[1]] == set():
                            #print 'bbbbbbb',tmp_dict,point
                            avail_points.append((dir,point))
                        #if tmp_dict[group[0]] == tmp_dict[group[1]] and tmp_dict[group[0]] != set([0,1,2,3]) and tmp_dict[group[0]] != set([0,1,2]) :
                        #    avail_points.append((dir,point))
                        elif len(tmp_dict[group[0]]) < 2 and len(tmp_dict[group[1]])< 2:
                            #print 'aaaaaaa',tmp_dict,point
                            avail_points.append((dir,point))

                index = 0
                
                avail_points_common = set(self.group2availpoint[group]) & set(avail_points)
                avail_points_uncommon = list(set(avail_points) - set(avail_points_common))

                ###debug
                #print group
                #for point in sorted(avail_points_common):
                #    print 'xxxxxxx',point
                #for point1 in sorted(avail_points_uncommon):
                #    print 'ttttttt',point1
                ####end debug

                net_num = len(sorted(self.dic_abuttingports[group]))/3
                #print self.dic_abuttingports['gc_tcri3_t', 'compute_array']
                print >>f,'#group:',group,len(avail_points),len(avail_points_common),len(avail_points_common) - net_num
                avail_points = sorted(avail_points_common,key = itemgetter(0,1)) + sorted(avail_points_uncommon,key = itemgetter(0,1))
                total_tracks = len(avail_points) - 1
                layer  = 0
                if net_num >= total_tracks:
                    avail_single = sorted(self.group2availpoint[group],key = itemgetter(0,1))
                    
                    for dir,point in avail_single:
                        tmp_point = point + self.pitch[dir]
                        tmp_dict = self.gen.dic_group2info[group].availpoints[dir].get(tmp_point,False)
                        if tmp_dict and tmp_dict[group[0]] == tmp_dict[group[1]]:
                            avail_points.append((dir,tmp_point))
                    total_tracks = len(avail_points) - 1
                    print >>f,'#Using single pitch:',len(avail_points),'Net num:',net_num

                        
                allow_set =    set(range(self.dic_allowlayer[dir]))
                for net in sorted(self.dic_abuttingports[group]):
                    port = [p.split('/')[-1] for p in self.dic_abuttingports[group][net]]
                    if port[0] not in self.dic_mastertile2location[mastergroup[0]] and port[1] not in self.dic_mastertile2location[mastergroup[1]]:
                        if index <= total_tracks:dir,point = avail_points[index]
                        max_layer_num = self.dic_allowlayer[dir]
                        if layer == (max_layer_num - 1): index += 1
                        layer = (layer+1)%max_layer_num
                        if index <= total_tracks:
                            dir,point = avail_points[index]
                        else:
                            #self.dic_abut2portloc[group][net] = port
                            self.dic_mastertile2constraintlocation[mastergroup[0]][port[0]] = self.dic_group2side[group][group[0]]
                            self.dic_mastertile2constraintlocation[mastergroup[1]][port[1]] = self.dic_group2side[group][group[1]]
                            print >>f,'No track for ports %s'  % port
                            break
                        valid = True
                        while(layer in self.gen.dic_group2info[group].availpoints[dir][point][group[1]] or layer in self.gen.dic_group2info[group].availpoints[dir][point][group[0]]):
                            if 'Single' in self.gen.dic_group2info[group].availpoints[dir][point][group[1]]:
                                allow_set  = set(range(self.dic_allowlayer[dir]))
                                if index <= total_tracks - 2:
                                    if len(allow_set & self.gen.dic_group2info[group].availpoints[dir][point][group[1]]) > self.dic_allowlayer[dir] -1:
                                        index += 1
                                        dir,point = avail_points[index]
                                        layer = 0
                                    else:
                                        if layer == self.dic_allowlayer[dir] - 1:
                                            index += 1
                                        layer = (layer+1)%self.dic_allowlayer[dir]
                                    continue
                                else:
                                    #self.dic_abut2portloc[group][net] = port
                                    self.dic_mastertile2constraintlocation[mastergroup[0]][port[0]] = self.dic_group2side[group][group[0]]
                                    self.dic_mastertile2constraintlocation[mastergroup[1]][port[1]] = self.dic_group2side[group][group[1]]
                                    print >>f,'No track for ports %s'  % port
                                    valid = False
                                    break    
                            if layer == self.dic_allowlayer[dir] - 1: 
                                index += 1
                                if index <= total_tracks:
                                    dir,point = avail_points[index]
                                else:
                                    #self.dic_abut2portloc[group][net] = port
                                    self.dic_mastertile2constraintlocation[mastergroup[0]][port[0]] = self.dic_group2side[group][group[0]]
                                    self.dic_mastertile2constraintlocation[mastergroup[1]][port[1]] = self.dic_group2side[group][group[1]]
                                    print >>f,'No track for ports %s'  % port
                                    valid = False
                                    break
                            layer = (layer+1)%self.dic_allowlayer[dir]
                        if 'Single' in self.gen.dic_group2info[group].availpoints[dir][point][group[1]] or 'Single' in self.gen.dic_group2info[group].availpoints[dir][point][group[0]]:
                            index += 1
                        if valid == False:continue
                        layer1 = layer0 = layer
                        dir0 = dir1 = dir
                        self.gen.dic_group2info[group].availpoints[dir][point][group[0]].add(layer0)
                        self.gen.dic_group2info[group].availpoints[dir][point][group[1]].add(layer1)
                        masterpoint0 = self.gen.dic_group2info[group].group2set[dir][group[0]][point]
                        masterpoint1 = self.gen.dic_group2info[group].group2set[dir][group[1]][point]

                        if masterpoint0 == masterpoint1:
                            orient1 = self.shape.dic_tiles[group[0]].inst_orient
                            orient2 = self.shape.dic_tiles[group[1]].inst_orient
                            if orient1 == orient2: 
                                continue
                            while(layer1 in self.gen.dic_group2info[group].availpoints[dir1][point][group[1]]):
                                if layer1 == self.dic_allowlayer[dir] - 1: 
                                    index += 1
                                    if index <= total_tracks :
                                        dir1,point = avail_points[index]
                                    else:
                                        #self.dic_abut2portloc[group][net] = port
                                        self.dic_mastertile2constraintlocation[mastergroup[1]][port[1]] = self.dic_group2side[group][group[1]]
                                        print >>f,'E03:No track for ports %s'  % port
                                        break
                                layer1 = (layer1+1)%self.dic_allowlayer[dir]
                            self.gen.dic_group2info[group].availpoints[dir1][point][group[0]].add(layer1)
                            self.gen.dic_group2info[group].availpoints[dir1][point][group[1]].add(layer1)
                            masterpoint1 = self.gen.dic_group2info[group].group2set[dir1][group[1]][point]
                        layer = layer1
                        self.dic_mastertile2location[mastergroup[0]][port[0]] = (masterpoint0,layer0,dir0)
                        self.dic_mastertile2location[mastergroup[1]][port[1]] = (masterpoint1,layer1,dir1)
                        #self.dic_abut2portloc[group][net] = [masterpoint0,masterpoint1]
                        print >>f, 'N00:Tile: %-15s Port: %-82s %-10s  %-10s %-10s %-10s %-5s' %(group[0],port[0],point,masterpoint0[0],masterpoint0[1],layer0,index)
                        print >>f, 'N00:Tile: %-15s Port: %-82s %-10s  %-10s %-10s %-10s %-5s' %(group[1],port[1],point,masterpoint1[0],masterpoint1[1],layer1,index)
                            
                            
                    elif port[0] in self.dic_mastertile2location[mastergroup[0]] and port[1] in self.dic_mastertile2location[mastergroup[1]]:
                        masterpoint0, layer0, diruseless= self.dic_mastertile2location[mastergroup[0]][port[0]]
                        masterpoint1, layer1, diruseless= self.dic_mastertile2location[mastergroup[1]][port[1]]
                        dirs = self.gen.dic_group2info[group].availpoints.keys()
                        point0 = point1 = '-!-'
                        for d in dirs:
                            if masterpoint0 in self.gen.dic_group2info[group].group2set_reversed[d][group[0]]:
                                point0 = self.gen.dic_group2info[group].group2set_reversed[d][group[0]][masterpoint0]
                            if masterpoint1 in self.gen.dic_group2info[group].group2set_reversed[d][group[1]]:
                                point1 = self.gen.dic_group2info[group].group2set_reversed[d][group[1]][masterpoint1] 
                                break
                        
                        #self.dic_abut2portloc[group][net] = [masterpoint0,masterpoint1]
                        print >>f, 'E01:Tile: %-15s Port: %-82s %-10s  %-10s %-10s %-10s' %(group[0],port[0],point0,masterpoint0[0],masterpoint0[1],layer0)
                        print >>f, 'E01:Tile: %-15s Port: %-82s %-10s  %-10s %-10s %-10s' %(group[1],port[1],point1,masterpoint1[0],masterpoint1[1],layer1)

                    elif port[0] in self.dic_mastertile2location[mastergroup[0]]:
                        masterpoint0,layer0 ,diruseless= self.dic_mastertile2location[mastergroup[0]][port[0]]
                        dirs = self.gen.dic_group2info[group].availpoints.keys()
                        point0 = point1 = '-!-'
                        masterpoint1 = ('#','#')
                        layer1 = layer0
                        for d in dirs:
                            if  masterpoint0  in  self.gen.dic_group2info[group].group2set_reversed[d][group[0]]:
                                dir = d
                                point0 = self.gen.dic_group2info[group].group2set_reversed[d][group[0]][masterpoint0]
                                break
                        point1 = point0
                        if point1 not in self.gen.dic_group2info[group].availpoints[dir]:
                            print >>f,'Error00: Connectivity conflict:',group,port,point1,'range:',min(self.gen.dic_group2info[group].availpoints[dir]),max(self.gen.dic_group2info[group].availpoints[dir]),"point:",point0,"Master point:",masterpoint0

                            self.dic_mastertile2constraintlocation[mastergroup[1]][port[1]] = self.dic_group2side[group][group[1]]
                            continue
                        
                        if layer1 not in self.gen.dic_group2info[group].availpoints[dir][point1][group[1]]:
                            masterpoint1 = self.gen.dic_group2info[group].group2set[dir][group[1]][point1]
                        else:
                            valid = True
                            print>>f,'NE:Find neareast point,orignal:',point1,layer1
                            index_1 = dic_dir2sortedpoints[group][dir].index(point1)
                            shift = 1
                            llength = len(dic_dir2sortedpoints[group][dir])
                            while(layer1 in self.gen.dic_group2info[group].availpoints[dir][point1][group[1]]):
                                if layer1 == self.dic_allowlayer[dir] - 1: 
                                    index_1 +=  (shift%2*2-1)*shift
                                    shift += 1
                                    if index_1 < llength:
                                        point1 = dic_dir2sortedpoints[group][dir][index_1]
                                    elif shift < llength:
                                        continue
                                    else:
                                        print >>f,'No track for ports %s'  % port, group
                                        self.dic_mastertile2constraintlocation[mastergroup[1]][port[1]] = self.dic_group2side[group][group[1]]
                                        valid = False
                                        break
                                layer1 = (layer1+1)%self.dic_allowlayer[dir]
                                
                            if valid == False: continue
                            masterpoint1 = self.gen.dic_group2info[group].group2set[dir][group[1]][point1]
                        self.gen.dic_group2info[group].availpoints[dir][point1][group[1]].add(layer1)
                        self.dic_mastertile2location[mastergroup[1]][port[1]] = (masterpoint1,layer1,dir)
                        #self.dic_abut2portloc[group][net] = [masterpoint0,masterpoint1]
                        print >>f, 'E03:Tile: %-15s Port: %-82s %-10s  %-10s %-10s %-10s' %(group[0],port[0],point0,masterpoint0[0],masterpoint0[1],layer0)
                        print >>f, 'N03:Tile: %-15s Port: %-82s %-10s  %-10s %-10s %-10s' %(group[1],port[1],point1,masterpoint1[0],masterpoint1[1],layer1)
                    elif port[1] in self.dic_mastertile2location[mastergroup[1]]:
                        masterpoint1,layer1 ,diruseless= self.dic_mastertile2location[mastergroup[1]][port[1]]
                        dirs = self.gen.dic_group2info[group].availpoints.keys()
                        point0 = point1 = '-!-'
                        masterpoint0 = ('#','#')
                        layer0  = layer1
                        for d in dirs:
                            if masterpoint1  in  self.gen.dic_group2info[group].group2set_reversed[d][group[1]]:
                                dir = d
                                point1 = self.gen.dic_group2info[group].group2set_reversed[d][group[1]][masterpoint1]
                                break
                        point0 = point1
                        if point0 not in self.gen.dic_group2info[group].availpoints[dir]:
                            print >>f,'Error01: Connectivity conflict:',group,port,point0,'range:',min(self.gen.dic_group2info[group].availpoints[dir]),max(self.gen.dic_group2info[group].availpoints[dir])
                            self.dic_mastertile2constraintlocation[mastergroup[0]][port[0]] = self.dic_group2side[group][group[0]]
                            continue
                        
                        if  layer0 not in self.gen.dic_group2info[group].availpoints[dir][point0][group[0]]:
                            masterpoint0 = self.gen.dic_group2info[group].group2set[dir][group[0]][point0]
                        else:  
                            valid = True
                            shift = 1
                            llength = len(dic_dir2sortedpoints[group][dir])
                            print>>f,'NE:Find neareast point,orignal:',point0,layer0
                            index_0 = dic_dir2sortedpoints[group][dir].index(point0)
                            while(layer0 in self.gen.dic_group2info[group].availpoints[dir][point0][group[0]]):
                                if layer0 == self.dic_allowlayer[dir] - 1: 
                                    index_0 +=  (shift%2*2-1)*shift
                                    shift += 1
                                    if index_0 < llength:
                                        point0 = dic_dir2sortedpoints[group][dir][index_0]
                                    elif shift < llength:
                                        continue
                                    else:
                                        print >>f,'No track for ports %s'  % port,group
                                        self.dic_mastertile2constraintlocation[mastergroup[0]][port[0]] = self.dic_group2side[group][group[0]]
                                        valid = False
                                        break
                                layer0 = (layer0 + 1)%self.dic_allowlayer[dir]
                            if valid == False: continue
                            masterpoint0 = self.gen.dic_group2info[group].group2set[dir][group[0]][point0]
                        self.gen.dic_group2info[group].availpoints[dir][point0][group[0]].add(layer0)        
                        self.dic_mastertile2location[mastergroup[0]][port[0]] = (masterpoint0,layer0,dir)
                        #self.dic_abut2portloc[group][net] = [masterpoint0,masterpoint1]
                        print >>f, 'N04:Tile: %-15s Port: %-82s %-10s  %-10s %-10s %-10s' %(group[0],port[0],point0,masterpoint0[0],masterpoint0[1],layer0)
                        print >>f, 'E04:Tile: %-15s Port: %-82s %-10s  %-10s %-10s %-10s' %(group[1],port[1],point1,masterpoint1[0],masterpoint1[1],layer1)
                    
        f.close()
    def update_abut_avail(self,dir,group,tile):
        mastertile = self.shape.dic_inst2master[tile]
        for port in self.dic_mastertile2location[mastertile]:
            masterpoint,layer,d = self.dic_mastertile2location[mastertile][port]
            if masterpoint  in self.gen.dic_group2info[group].group2set_reversed[dir][tile]:
                point = self.gen.dic_group2info[group].group2set_reversed[dir][tile][masterpoint]
                if point not in self.gen.dic_group2info[group].availpoints[dir]:continue
                self.gen.dic_group2info[group].availpoints[dir][point][tile].add(layer)
    def update_net_avail(self,dir,group,tile):
        mastertile = self.shape.dic_inst2master[tile]
        for port in self.dic_mastertile2location_net[mastertile]:
            masterpoint,layer,d = self.dic_mastertile2location_net[mastertile][port]
            if masterpoint  in self.gen.dic_group2info[group].group2set_reversed[dir][tile]:
                point = self.gen.dic_group2info[group].group2set_reversed[dir][tile][masterpoint]
                if point not in self.gen.dic_group2info[group].availpoints[dir]:continue
                self.gen.dic_group2info[group].availpoints[dir][point][tile].add(layer)
            
    def update_avail(self,dir,group,tile):
        mastertile = self.shape.dic_inst2master[tile]
        for port in self.dic_mastertile2location[mastertile]:
            masterpoint,layer,d = self.dic_mastertile2location[mastertile][port]
            if masterpoint  in self.gen.dic_group2info[group].group2set_reversed[dir][tile]:
                point = self.gen.dic_group2info[group].group2set_reversed[dir][tile][masterpoint]
                if point not in self.gen.dic_group2info[group].availpoints[dir]:continue
                self.gen.dic_group2info[group].availpoints[dir][point][tile].add(layer)
        for masterpoint in self.dic_mastertile2skiplocation[mastertile]:
            if masterpoint  in self.gen.dic_group2info[group].group2set_reversed[dir][tile]:
                point = self.gen.dic_group2info[group].group2set_reversed[dir][tile][masterpoint]
                if point in self.gen.dic_group2info[group].availpoints[dir]:
                    self.gen.dic_group2info[group].availpoints[dir][point][tile].add(4)
                if point + self.pitch[dir] in self.gen.dic_group2info[group].availpoints[dir]:
                    self.gen.dic_group2info[group].availpoints[dir][point+ self.pitch[dir]][tile].add(4)
    def get_side(self):
        '''
            Get side infomation
            group -> tile -> side list
        '''
        self.dic_group2side = defaultdict(dict)
        for tile in self.shape.dic_tiles:
            for abut in self.shape.dic_tiles[tile].abut_inst:
                group  = (tile,abut[-2])
                ref_edge0 = self.shape.dic_inst2ref[tile][abut[0]]
                ref_edge1 = self.shape.dic_inst2ref[abut[-2]][abut[1]]
                if group in self.dic_group2side and tile in self.dic_group2side[group]:
                    self.dic_group2side[group][tile].append(self.shape.dic_master2edgeside[self.shape.dic_inst2master[tile]][ref_edge0])
                else:
                    self.dic_group2side[group][tile] = [self.shape.dic_master2edgeside[self.shape.dic_inst2master[tile]][ref_edge0]]
                if group in self.dic_group2side and abut[-2] in self.dic_group2side[group]:
                    self.dic_group2side[group][abut[-2]].append(self.shape.dic_master2edgeside[self.shape.dic_inst2master[abut[-2]]][ref_edge1])
                else:
                    self.dic_group2side[group][abut[-2]] = [self.shape.dic_master2edgeside[self.shape.dic_inst2master[abut[-2]]][ref_edge1]]
                
    def align_number(self,num,dic_golden_info):
        for i in range(num):
            same_dir = []
            tmp = 0
            if i < len(port) -1 and max_dir[i/2] == max_dir[(i+1)/2]:
                same_dir.append(i)
            else:
                if i == len(port) -1:
                    same_dir.append(i)
                for j in same_dir:
                    if j in dic_golden_info:
                        dic_golden_info[same_dir[0]] = dic_golden_info[j]
                for j in same_dir:
                    if j in dic_golden_info:
                        tmp = dic_golden_info[j]
                    else:
                        dic_golden_info[j] = tmp

                same_dir = [i]
        return dic_golden_info

#    def preblocktrack(self):
#        '''
#            Block interfacing tracks of pre assign ports
#        '''
#        for group in self.gen.dic_group2info:
#            for tile in group:
#                master = self.shape.dic_inst2master[tile]
#                master_point = set(self.gen.dic_group2info[group].group2set_reversed)

    def special_assignment(self,test = True):
        '''
            tune format:
                ^df.* ^df.* si
                ^df.* ^df.* str
            test = True Only assign groups in the tune
            si means It will assign a driver pin followed by a load pin
            str means ports would be sorted by port name
        '''
        print 'Start process special assignment'
        self.only_special = test
        self.dic_special_topo2port = defaultdict(list)
        with  mkdir('placecollapsepins/si_aware.tune',type = 'tunes',mode = 'r+') as f:
            self.dic_special_assignment = {}
            for line in f:
                if '#' in line: continue
                a,b,method = line.split()
                a,b = re.compile(a),re.compile(b)
                A = []
                B = []
                for tile in self.shape.dic_master2inst:
                    if a.search(tile):
                        A.append(tile)
                    if b.search(tile):
                        B.append(tile)
                for i in A:
                    for j in B:
                        self.dic_special_assignment[(i,j)] = method
                        self.dic_special_assignment[(j,i)] = method
        for mastergroup in self.dic_special_assignment:
            mastergroup_r  = tuple(reversed(list(mastergroup)))
            if mastergroup in self.dic_topo and mastergroup_r in self.dic_topo:
                for topo in self.dic_topo[mastergroup]:
                    if topo in self.dic_special_topo2port: continue
                    ports = sorted(self.dic_topo2port[topo])
                    topo_r = tuple(reversed(list(topo)))
                    if topo_r in self.dic_topo2port:
                        ports_r = []
                        for port in self.dic_topo2port[topo_r]:
                            ports_r.append(tuple(reversed(list(port))))
                        ports_r = sorted(ports_r)
                    else:
                        ports_r = []
                        i = 0
                    for i in range(0,min((len(ports),len(ports_r)))):
                        self.dic_special_topo2port[topo].append(ports[i])
                        self.dic_special_topo2port[topo].append(ports_r[i])
                        if not (i*2+2)%6: 
                            for j in range(3):
                                self.dic_special_topo2port[topo].append(tuple([p + 'HACKPP_' + str(j) for p in ports[i] ]))
                    remain = ports[i:] + ports_r[i:]
                    for i in range(len(remain)):
                        self.dic_special_topo2port[topo].append(remain[i])
                        if not (i % 6):
                            self.dic_special_topo2port[topo].append(tuple( [p + 'HACKPP_remain' + str(i) for p in remain[i]]))

        print 'End process special assignment'
                        
                    
                
    def placefeedports(self):
        '''
            place feed ports
        '''
        
        
        mastergrouporder = defaultdict(int)
        preassignset = set(self.dic_mastertile2location)
        #
        self.get_allow_single()
        self.align_direction()
        self.get_feedorder()
        i = len(self.dic_mastergroup2feedsequence)
        j = i
        for mastergroup in self.dic_topo['mastergroup']:
            i += 1
            if mastergroup in self.dic_special_assignment:
                mastergrouporder[mastergroup] = j
            if set(mastergroup) & preassignset:
                mastergrouporder[mastergroup] = j
            else:
                mastergrouporder[mastergroup] = i
            if mastergroup in self.dic_mastergroup2feedsequence:
               mastergrouporder[mastergroup] = self.dic_mastergroup2feedsequence[mastergroup]

        self.dic_mastertile2skiplocation = defaultdict(dict)
        self.dic_mastertile2usedlocation = defaultdict(dict)
        
        for master in self.dic_mastertile2location:
            for port in self.dic_mastertile2location[master]:
                loc = tuple(self.dic_mastertile2location[master][port][0:2])
                self.dic_mastertile2usedlocation[master][loc] = ''
        
        f = mkdir_open('placecollapsepins/placefeedports.rpt')
        total_mastergroup = len(self.dic_topo['mastergroup'])
        finish = 1
        dic_topo2reuseedge = self.dic_topo['topo2reuseedge']
        self.fakeabut = defaultdict(list)
        for mastergroup,nu in sorted(mastergrouporder.items(), key = lambda x:x[1]):
            ######sby
            #break
            print '%d/%d finished...Now: %s' %(finish,total_mastergroup,mastergroup)
            finish += 1
            if self.only_special: 
                if mastergroup not in self.dic_special_assignment:
                    print >>f, 'Skip',mastergroup
                    continue
                
            if mastergroup not in self.dic_topo:
                print >>f,mastergroup,'skipped'
                self.fakeabut[mastergroup] = self.dic_mastergroup2topo[mastergroup]
                continue
            print >>f,'#Starting:',mastergroup,finish
            maxstep = self.dic_group2maxstep[mastergroup]

            topos = self.dic_topo[mastergroup].keys()
           # print topos
           # print "aaa"
           # print self.dic_mastergroup2feedorder
           # print "bbb"
            if mastergroup in self.dic_mastergroup2feedorder:
                first = []
                for topo in self.dic_mastergroup2feedorder[mastergroup]:
                    if topo in topos:
                        first.append(topo)
                        topos.remove(topo)
                topos = first +topos
            for topo in topos: 
                
                dic_step = self.dic_topo2step[topo]
                mastertopo = tuple([self.shape.dic_inst2master[m] for m in topo])
                if (mastertopo[0],mastertopo[-1]) != mastergroup:
                    #only assign topo belong to the mastergroup
                    continue
                mastertopo_hack = [mastertopo[0]] + list(mastertopo) + [mastertopo[-1]]# if number of tile > 2, means it used twice
                dic_skipcheck = {topo[i]:''for i in reversed(range(len(topo))) if mastertopo_hack.count(mastertopo[i]) > 2}
                        
                abut_group = self.dic_topo[mastergroup][topo]['abut_group']
                max_dir = self.dic_topo[mastergroup][topo]['max_dir']
                allow_point = self.dic_topo[mastergroup][topo]['allow_point']
                dic_tile2id = {}
                id_ = [0]
                for dir_id in range(len(max_dir)-1):
                    if max_dir[dir_id] !=  max_dir[dir_id+1]:
                       id_.append(dir_id+1)
                id_.append(dir_id+2)
                for i in range(1,len(id_)):
                    for j in range(id_[i-1],id_[i]):
                        dic_tile2id[j*2] = id_[i]*2 - 1
                        dic_tile2id[j*2+1] = id_[i]*2 - 1 
                print >>f,'#Index:', sorted(dic_tile2id.items())
                

                for i in range(len(abut_group)):
                    group = abut_group[i]
                    if group not in self.gen.dic_group2info:
                        self.gen.dic_group2info[group] = type(' '.join(group),(),{'routedir':{0:0},
                                'max_dir':0,
                                'group2point':dict(),
                                'group2set':{0:{t:tuple() for t in group}},
                                'group2set_reversed':{0:{t:tuple() for t in group}},
                                'groupname':group,
                                'availpoints':{0:dict()},
                                'group2loc':{t:tuple() for t in group}
                                
                                })
                    #self.update_avail(max_dir[i],group,group[0])
                    #self.update_avail(max_dir[i],group,group[1])
                #filter topo with no track
                test_valid = [len(g) for g in allow_point]
                if 0 in test_valid or test_valid == []:
                    self.fakeabut[mastergroup].append(topo)
                    continue
                ###check if port was placed
                port_index = 0
                port_index_range = []
                port_placed = False
                port_unplaced = []
                
                golden_layer = 0
                golden_point_index = 1
                print >>f,topo
                dic_golden_lastinfo = {num: (0,0) for num in range(len(topo))}
                PORTS = self.dic_special_topo2port[topo] if topo in self.dic_special_topo2port else sorted(self.dic_topo2port[topo])
                for port in PORTS:
                    dic_golden_info = {}
                    port_placed = False
                    net_name = port[0]
                    for i in range(len(port)):
                        mastertile = self.shape.dic_inst2master[topo[i]]
                        if port[i] in self.dic_mastertile2location[mastertile]:
                            port_index = i
                            port_placed = True
                            master = mastertopo[port_index]
                            masterpoint,golden_layer,diruseless = self.dic_mastertile2location[master][port[port_index]]
                            point = self.gen.dic_group2info[abut_group[port_index/2]].group2set_reversed[max_dir[port_index/2]][topo[port_index]].get(masterpoint,'-!-')
                            if point == '-!-':
                                other_dir = (max_dir[port_index/2]+1)%2

                                if other_dir in self.gen.dic_group2info[abut_group[port_index/2]].group2set_reversed and self.gen.dic_group2info[abut_group[port_index/2]].group2set_reversed[other_dir].keys():
                                   point =  self.gen.dic_group2info[abut_group[port_index/2]].group2set_reversed[other_dir][topo[port_index]].get(masterpoint,'-!-')
                                if point == '-!-':
                                    print >>f,'#Port:  pre assigned port not on current abutting edge', port[i],abut_group[i/2],diruseless
                                    print >>f,max_dir[i/2],min(allow_point[i/2]),max(allow_point[i/2])
                                    continue
                                else:
                                    max_dir[port_index/2] = other_dir
                                    abut_set0 = set(self.gen.dic_group2info[abut_group[i/2]].availpoints[other_dir])
                                    sort_dir =  False if  allow_point[i/2][-1] - allow_point[i/2][0] > 0 else True
                                    allow_point[i/2] = tuple(sorted(abut_set0,reverse = sort_dir))

                            elif point  < min(allow_point[port_index/2]) or point > max(allow_point[port_index/2]):
                                print >>f,'#Port:  pre assigned port out of common abutting edge', port[i],abut_group[i/2]
                                sort_dir =  False if  allow_point[i/2][-1] - allow_point[i/2][0] > 0 else True
                                group2loc = self.gen.dic_group2info[abut_group[i/2]].group2loc[topo[i]]
                                abut_set0 = set(self.gen.dic_group2info[abut_group[i/2]].availpoints[max_dir[i/2]])
                                abut_set = abut_set0 & set(dic_topo2reuseedge[topo].get(mastertopo[i],{}).get(group2loc,set()))
                                if abut_set:
                                    abut_set = abut_set|set(allow_point[i/2])
                                    a,b,c,d,e = max(abut_set),min(abut_set),max(allow_point[i/2]),min(allow_point[i/2]),len(allow_point[i/2])
                                    if a == c and b ==d:
                                        allow_point[i/2] = tuple(sorted(abut_set0,reverse = sort_dir))
                                        print >>f,"Expand00: using all available points"
                                    else:
                                        print >>f,"Expand00: new:",abut_group[i/2],a,b,'old:',c,d,e
                                    
                                        allow_point[i/2] = tuple(sorted(abut_set,reverse = sort_dir))
                                else:
                                    allow_point[i/2] = tuple(sorted(abut_set0,reverse = sort_dir))
                                    print >>f,"Expand00: using all available points"
                                
                            try:
                                golden_point_index = allow_point[port_index/2].index(point)
                            except:
                                sort_dir =  False if  allow_point[i/2][-1] - allow_point[i/2][0] > 0 else True
                                tmp = list(allow_point[i/2])
                                tmp.append(point)
                                tmp = sorted(tmp,reverse = sort_dir)
                                golden_point_index = tmp.index(point)
                                if golden_point_index == 0:
                                   golden_point_index = 0
                                elif golden_point_index == len(tmp) - 1:
                                    golden_point_index = len(allow_point[i/2]) - 1
                                else:
                                    b = golden_point_index - 1
                                    a = golden_point_index + 1
                                    if abs(allow_point[port_index/2][a] - point) > abs(allow_point[port_index/2][b] - point):
                                        golden_point_index = b

                            dic_golden_info[i] = (golden_point_index,golden_layer)

                    if port_placed == False:
                        port_unplaced.append(port)
                        continue
                    #Starting assign placed ports
                    dic_golden_infoalign = copy.deepcopy(dic_golden_info)
                    same_dir = []
                    mastergroup_reverse = (mastergroup[-1],mastergroup[0])
                    dic_golden_info_reverse = {}

                    if mastergroup_reverse in self.dic_align_direction:
                        length = len(port) - 1
                        for index in dic_golden_info:
                            dic_golden_info_reverse[length - index] = dic_golden_info[index]
                        dic_golden_info = dic_golden_info_reverse
                        max_dir.reverse()
                        
                    for i in range(len(port)):
                        if i%2:
                            if i - 1 not in dic_golden_info and i in dic_golden_info:
                                dic_golden_info[i-1] = dic_golden_info[i]
                        #tmp = (0,0)
                        tmp = dic_golden_lastinfo[i]
                        if i < len(port) -1 and max_dir[i/2] == max_dir[(i+1)/2]:
                            same_dir.append(i)
                        else:
                            same_dir.append(i)
                            for j in same_dir:
                                if j in dic_golden_info:
                                    dic_golden_info[same_dir[0]] = dic_golden_info[j]
                                    break
                            for j in same_dir:
                                if j in dic_golden_info:
                                    tmp = dic_golden_info[j]
                                else:
                                    dic_golden_info[j] = tmp
                        
                            same_dir = []
                    dic_golden_info_reverse = {}
                    if mastergroup_reverse in self.dic_align_direction:
                        length = len(port) - 1
                        for index in dic_golden_info:
                            dic_golden_info_reverse[length - index] = dic_golden_info[index]
                        dic_golden_info = dic_golden_info_reverse
                        max_dir.reverse()
                    print >>f,'#00:',sorted(dic_golden_infoalign.items())
                    print >>f,'#01:',sorted(dic_golden_info.items())
                    
                    #self.dic_feed2portloc[topo][net_name] = [] #init
                    self.dic_mastertile2location_net = defaultdict(dict)
                    #start

                    for i in range(len(port)):
                        valid = True                       
                        group = abut_group[i/2]
                        #if group[0] in dic_skipcheck:self.update_net_avail(max_dir[i/2],group,group[0])
                        #if group[1] in dic_skipcheck:self.update_net_avail(max_dir[i/2],group,group[1])
                        if port[i] in self.dic_mastertile2location[mastertopo[i]]:
                            masterpoint,layer,diruseless = self.dic_mastertile2location[mastertopo[i]][port[i]]
                            point = self.gen.dic_group2info[abut_group[i/2]].group2set_reversed[max_dir[i/2]][topo[i]].get(masterpoint,'-!-')

                            #self.dic_feed2portloc[topo][net_name].append(masterpoint)
                            print >>f,'E00:Tile: %-15s Port: %-82s %-10s  %-10s %-10s %-10s' %(':'.join([mastertopo[i],topo[i]]),port[i],point,masterpoint[0],masterpoint[1],layer)
                            if i < len(port) -1 and max_dir[i/2] == max_dir[(i+1)/2] and ((i+1)%2 or dic_golden_info[i+1] == (0,0) ):
                                if point == '-!-':
                                    print >>f,'#Port:  pre assigned port not on current abutting edge', port[i],abut_group[i/2]

                                    continue
                                elif point  < min(allow_point[i/2]) or point > max(allow_point[i/2]):
                                    print >>f,'#Port:  pre assigned port out of common abutting edge', port[i],abut_group[i/2]
                                    sort_dir =  False if  allow_point[i/2][-1] - allow_point[i/2][0] > 0 else True
                                    group2loc = self.gen.dic_group2info[abut_group[i/2]].group2loc[topo[i]]
                                    abut_set0 = set(self.gen.dic_group2info[abut_group[i/2]].availpoints[max_dir[i/2]])
                                    abut_set = abut_set0 & set(dic_topo2reuseedge[topo].get(mastertopo[i],{}).get(group2loc,set()))
                                    if abut_set:
                                        abut_set = abut_set|set(allow_point[i/2])
                                        a,b,c,d ,e = max(abut_set),min(abut_set),max(allow_point[i/2]),min(allow_point[i/2]),len(allow_point[i/2])
                                        if a == c and b ==d:
                                            allow_point[i/2] = tuple(sorted(abut_set0,reverse = sort_dir))

                                            print >>f,"Expand01: using all available points"
                                        else:
                                            print >>f,"Expand01: new:",abut_group[i/2],a,b,'old:',c,d,e

                                            allow_point[i/2] = tuple(sorted(abut_set,reverse = sort_dir))
                                    else:
                                        print >>f,"Expand01: using all available points"
                                        allow_point[i/2] = tuple(sorted(abut_set0,reverse = sort_dir))
                                try:
                                    point_index = allow_point[i/2].index(point)
                                except:
                                    sort_dir =  False if  allow_point[i/2][-1] - allow_point[i/2][0] > 0 else True
                                    tmp = list(allow_point[i/2])
                                    tmp.append(point)
                                    tmp = sorted(tmp,reverse = sort_dir)
                                    point_index = tmp.index(point)
                                    if point_index == 0:
                                       point_index = 0
                                    elif point_index == len(tmp) - 1:
                                        point_index = len(allow_point[i/2]) - 1
                                    else:
                                        b = point_index - 1
                                        a = point_index + 1
                                        if abs(allow_point[i/2][a] - point) > abs(allow_point[i/2][b] - point):
                                            point_index = b
                                dic_golden_info[i+1] = (point_index,layer)
                                        
                        else:
                            point_index,layer  = dic_golden_info[i]
                            if point_index <= len(allow_point[i/2]) - 1:
                                point = allow_point[i/2][point_index]
                            else:
                                sort_dir =  False if  allow_point[i/2][-1] - allow_point[i/2][0] > 0 else True
                                group2loc = self.gen.dic_group2info[abut_group[i/2]].group2loc[topo[i]]
                                abut_set0 = set(self.gen.dic_group2info[abut_group[i/2]].availpoints[max_dir[i/2]])
                                abut_set = abut_set0 & set(dic_topo2reuseedge[topo].get(mastertopo[i],{}).get(group2loc,set()))
                                if abut_set:
                                    abut_set = abut_set|set(allow_point[i/2])
                                    a,b,c,d,e = max(abut_set),min(abut_set),max(allow_point[i/2]),min(allow_point[i/2]),len(allow_point[i/2])
                                    if a == c and b ==d:
                                        allow_point[i/2] = tuple(sorted(abut_set0,reverse = sort_dir))
                                        print >>f,"Expand02: using all available points"
                                    else:
                                        print >>f,"Expand02: new:",abut_group[i/2],a,b,'old:',c,d,e
                                
                                        allow_point[i/2] = tuple(sorted(abut_set,reverse = sort_dir))
                                else:
                                    print >>f,"Expand02: using all available points"
                                    allow_point[i/2] = tuple(sorted(abut_set0,reverse = sort_dir))
                                if point_index <=  len(allow_point[i/2]) - 1:
                                    print >>f,'Port: %s has no golden track to be placed, expand edge'  % port[i]
                                    point = allow_point[i/2][point_index]
                                else:
                                    print >>f,'Port: %s has no golden track to be placed, turn round'  % port[i]
                                    #point_index = len(allow_point[i/2]) - 1##????
                                    point_index = 0
                                    point = allow_point[i/2][point_index]
                            max_search_point = len(allow_point[i/2]) - 3
                            used_search_point = 1
                            flag_change_edge = True
                            if i%2 == 0:
                                banset = self.dic_mastergroupofsingle.get(mastergroup,set(['Single'])) #if track is allowed
                                dir = max_dir[i/2]
                                max_layers = self.dic_allowlayer[dir]
                                avail =  set([max_layers - 1]) #track avail layer
                                threshold = 0
                                if i not in dic_golden_infoalign and i+1 not in dic_golden_infoalign:
                                    allow_track = set(range(max_layers))
                                    point_old = point
                                    point_index_old = point_index
                                    now_set_i = self.gen.dic_group2info[abut_group[i/2]].availpoints[max_dir[i/2]][point][topo[i]]
                                    now_set_i_1 = self.gen.dic_group2info[abut_group[(i+1)/2]].availpoints[max_dir[(i+1)/2]][point][topo[i+1]]
                                    shift = 2
                                    while(now_set_i & banset or len(now_set_i & avail) != threshold or len(now_set_i_1 & avail) != threshold):
                                    #while(now_set_i & banset or len(now_set_i_1 & avail) > 2 or len(now_set_i & avail) > 2):
                                        if used_search_point < max_search_point:
                                            #point_index += 1
                                            point_index  =  (shift%2*2 -1)*shift/2 + point_index_old
                                            shift += 1
                                            ##change--11/26
                                            if point_index <= max_search_point:
                                                point_index = point_index%max_search_point
                                            else :
                                                point_index = max_search_point
                                            used_search_point += 1
                                        elif flag_change_edge:
                                            other_dir = (max_dir[i/2]+1)%2
                                            if other_dir in self.gen.dic_group2info[abut_group[i/2]].group2set_reversed and self.gen.dic_group2info[abut_group[i/2]].group2set_reversed[other_dir].keys():
                                                max_dir[i/2] = other_dir
                                                abut_set0 = set(self.gen.dic_group2info[abut_group[i/2]].availpoints[other_dir])
                                                sort_dir =  False if  allow_point[i/2][-1] - allow_point[i/2][0] > 0 else True
                                                allow_point[i/2] = tuple(sorted(abut_set0,reverse = sort_dir))
                                                max_search_point = len(allow_point[i/2]) - 3
                                                point_index = 0
                                            flag_change_edge = False
                                        else:
                                            if len(allow_track) == max_layers:
                                                sort_dir =  False if  allow_point[i/2][-1] - allow_point[i/2][0] > 0 else True
                                                group2loc = self.gen.dic_group2info[abut_group[i/2]].group2loc[topo[i]]
                                                abut_set0 = set(self.gen.dic_group2info[abut_group[i/2]].availpoints[max_dir[i/2]])
                                                abut_set = abut_set0 & set(dic_topo2reuseedge[topo].get(mastertopo[i],{}).get(group2loc,set()))
                                                if abut_set:    
                                                    abut_set = abut_set|set(allow_point[i/2])
                                                    a,b,c,d,e = max(abut_set),min(abut_set),max(allow_point[i/2]),min(allow_point[i/2]),len(allow_point[i/2])
                                                    if a == c and b ==d:
                                                        allow_point[i/2] = tuple(sorted(abut_set0,reverse = sort_dir))
                                                        print >>f,"Expand03: using all available points"
                                                    else:
                                                        print >>f,"Expand03: new:",abut_group[i/2],a,b,'old:',c,d,e
                                                        allow_point[i/2] = tuple(sorted(abut_set,reverse = sort_dir))
                                                else:
                                                    print >>f,"Expand03: using all available points"
                                                    allow_point[i/2] = tuple(sorted(abut_set0,reverse = sort_dir))
                                                max_search_point = len(allow_point[i/2]) - 3
                                                allow_track.add('Change_side')
                                            else:
                                                if 'Change_side' in allow_track: allow_track.discard('Change_side')
                                                if allow_track:
                                                    avail = set(range(max_layers))
                                                    banset = set()
                                                    threshold = self.dic_allowlayer[dir] - len(allow_track)
                                                    allow_track.pop()
                                                else:
                                                    break
                                            used_search_point = 1
                                        point = allow_point[i/2][point_index]
                                        now_set_i = self.gen.dic_group2info[abut_group[i/2]].availpoints[max_dir[i/2]][point][topo[i]]
                                        now_set_i_1 = self.gen.dic_group2info[abut_group[(i+1)/2]].availpoints[max_dir[(i+1)/2]][point][topo[i+1]]
                                        #bebug
                                        #if port[i] == "Src137_CreditRecvRdy":print >>f,point_index,point,now_set_i,now_set_i_1
                                    if used_search_point == max_search_point:
                                        point_index = point_index_old
                                        point = point_old
                                        if flag_change_edge == False:
                                            other_dir = (max_dir[i/2]+1)%2
                                            if other_dir in self.gen.dic_group2info[abut_group[i/2]].group2set_reversed and self.gen.dic_group2info[abut_group[i/2]].group2set_reversed[other_dir].keys():
                                                max_dir[i/2] = other_dir
                                                abut_set0 = set(self.gen.dic_group2info[abut_group[i/2]].availpoints[other_dir])
                                                sort_dir =  False if  allow_point[i/2][-1] - allow_point[i/2][0] > 0 else True
                                                allow_point[i/2] = tuple(sorted(abut_set0,reverse = sort_dir))
                                    else:
                                        if point != point_old:
                                            layer = 0
                                        point = allow_point[i/2][point_index]
                            ###binyou-national
                            if i%2 == 0 and port[i+1] in self.dic_mastertile2location[mastertopo[i+1]]:
                                masterpoint,layer,diruseless = self.dic_mastertile2location[mastertopo[i+1]][port[i+1]]
                                point = self.gen.dic_group2info[abut_group[i/2]].group2set_reversed[max_dir[i/2]][topo[i+1]].get(masterpoint,point)
                                try:
                                    if point in  allow_point[i/2]:
                                        point_index = allow_point[i/2].index(point)
                                    else:
                                        other_dir = (max_dir[i/2]+1)%2
                                        if other_dir in self.gen.dic_group2info[abut_group[i/2]].group2set_reversed and self.gen.dic_group2info[abut_group[i/2]].group2set_reversed[other_dir].keys():
                                            max_dir[i/2] = other_dir
                                            abut_set0 = set(self.gen.dic_group2info[abut_group[i/2]].availpoints[other_dir])
                                            sort_dir =  False if  allow_point[i/2][-1] - allow_point[i/2][0] > 0 else True
                                            allow_point[i/2] = tuple(sorted(abut_set0,reverse = sort_dir))
                                        point_index = allow_point[i/2].index(point)
                                except ValueError:
                                    print >>f,'Error00: assigned port is conflict'
                                    if i%2 == 0: 
                                        next_point = self.find_nearest(f,point,abut_group[i/2],topo[i],max_dir[i/2],layer)
                                        if next_point :
                                            masterpoint_n,layer_n,point_n = next_point
                                            self.gen.dic_group2info[abut_group[i/2]].availpoints[max_dir[i/2]][point_n][topo[i]].add(layer_n)
                                            self.dic_mastertile2location[mastertopo[i]][port[i]] = (masterpoint_n,layer_n,max_dir[i/2])
                                            print >>f,'N00:Tile: %-15s Port: %-82s %-10s  %-10s %-10s %-10s' %(':'.join([mastertopo[i],topo[i]]),port[i],point_n,masterpoint_n[0],masterpoint_n[1],layer_n)
                                            continue   
                            ###End
                            #print abut_group
                            now_set = self.gen.dic_group2info[abut_group[i/2]].availpoints[max_dir[i/2]][point][topo[i]]
                            shift = 2
                            used_search_point = 1
                            point_index_old = point_index
                            dir = max_dir[i/2]
                            while (layer in now_set ):
                                #print >>f,topo,now_set,point_index
                                if layer < self.dic_allowlayer[dir] - 1: 
                                    layer += 1
                                    continue
                                else:
                                    #The great formula developed by jiamliu
                                    #point_index  +=  (shift%2*2-1)*shift
                                    point_index  =  (shift%2*2 -1)*shift/2 + point_index_old
                                    if point_index >= 0 and point_index < max_search_point:
                                        used_search_point += 1
                                    else:
                                        shift += 1
                                        if used_search_point >= max_search_point:
                                            print >>f,'Port: %s has no track to be placed' % port[i]
                                            valid = False
                                            #self.dic_feed2portloc[topo][net_name].append(port[i])
                                            masterpoint = self.gen.dic_group2info[abut_group[i/2]].group2set[max_dir[i/2]][topo[i]][point]
                                            break
                                        continue
                                    shift += 1
                                    point = allow_point[i/2][point_index]
                                    now_set = self.gen.dic_group2info[abut_group[i/2]].availpoints[max_dir[i/2]][point][topo[i]]
                                    layer = 0
                            if valid:
                                self.gen.dic_group2info[abut_group[i/2]].availpoints[max_dir[i/2]][point][topo[i]].add(layer)
                                masterpoint = self.gen.dic_group2info[abut_group[i/2]].group2set[max_dir[i/2]][topo[i]][point]
                                self.dic_mastertile2location[mastertopo[i]][port[i]] = (masterpoint,layer,max_dir[i/2])
                                self.dic_mastertile2location_net[mastertopo[i]][port[i]] = (masterpoint,layer,max_dir[i/2])
                                self.dic_mastertile2usedlocation[mastertopo[i]][(masterpoint,layer)] = ''
                                self.dic_mastertile2skiplocation[mastertopo[i]][masterpoint] = ''
                                #self.dic_feed2portloc[topo][net_name].append(masterpoint)
                                print >>f,'N00:Tile: %-15s Port: %-82s %-10s  %-10s %-10s %-10s |%-10s%-10s' %(':'.join([mastertopo[i],topo[i]]),port[i],point,masterpoint[0],masterpoint[1],layer,dic_golden_info[i][0],point_index),self.gen.dic_group2info[abut_group[i/2]].availpoints[max_dir[i/2]][point][topo[i]]
                                dic_golden_lastinfo[i] = (point_index,layer)
                                if i%2 == 0:
                                    dic_golden_info[i+1] = (point_index,layer)
                                #elif i < len(port) - 1 and dic_golden_info[i+1] == (0,0) and max_dir[i/2] == max_dir[(i+1)/2]:
                                elif i < len(port) - 1 and i+1 not in dic_golden_infoalign and i + 2 not in dic_golden_infoalign and max_dir[i/2] == max_dir[(i+1)/2] and mastergroup_reverse not in self.dic_align_direction:
                                    dic_golden_info[i+1] = (point_index,layer)
                                    
                                #for j in range(len(abut_group)):
                                #    group = abut_group[j]
                                #    self.update_net_avail(max_dir[j],group,group[0])
                                #    self.update_net_avail(max_dir[j],group,group[1])
                                
                            else:
                                self.dic_mastertile2constraintlocation[mastertopo[i]][port[i]] = self.dic_group2side[abut_group[i/2]][topo[i]]
                layer_all = [0]*len(topo)
                point_index_all =  [1]*len(topo)
                dic_index2loop = defaultdict(int)
                dic_expand2loop = defaultdict(int) #

                for port in port_unplaced:
                    dic_master2point = {}
                    net_name = port[0]
                    #self.dic_feed2portloc[topo][net_name] = [] #init
                    self.dic_mastertile2location_net = defaultdict(dict)
                    step = maxstep
                    print >>f,'Step by pins:',step,maxstep,mastergroup
                    print >>f,point_index_all,layer_all
                    print >>f,dic_expand2loop,dic_index2loop
                    banset = set(['Single'])
                    block = set(['Single', 4])
                    for i in range(len(port)):
                        group = abut_group[i/2]
                        #if group[0] in dic_skipcheck:self.update_net_avail(max_dir[i/2],group,group[0])
                        #if group[1] in dic_skipcheck:self.update_net_avail(max_dir[i/2],group,group[1])
                        if dic_index2loop[i] >= 1 or (i%2 and dic_index2loop[i-1] >= 1) or banset == set() or (i%2 and block == set()):
                            block =  set()
                        else:
                            block =  set(['Single',4]) # It will change if single pitch used
                        limit = self.dic_allowlayer[max_dir[i/2]]
                        block_golden = set(['Single',4])
                        point_index = point_index_all[i]
                        layer = layer_all[i]
                        valid = True #whether layer and point is vaild for port[i]
                            
                        if port[i] in self.dic_mastertile2location[mastertopo[i]]:
                            masterpoint,layer,diruseless = self.dic_mastertile2location[mastertopo[i]][port[i]]
                            point = self.gen.dic_group2info[abut_group[i/2]].group2set_reversed[max_dir[i/2]][topo[i]].get(masterpoint,'-!-')
                            #self.dic_feed2portloc[topo][net_name].append(masterpoint)
                            try:
                                point_index = allow_point[i/2].index(point)
                                if i%2 == 0: point_index_all[1+i] = point_index
                            except ValueError:
                                print >>f,'Error02: assigned port is conflict'
                                if i%2 == 0: 
                                    #print >>f,'#',self.gen.dic_group2info[('umc_umcch_t33','umc_umcch_t31')].availpoints[0][4678240]['umc_umcch_t31']
                                    next_point= self.find_nearest(f,point,abut_group[i/2],topo[i+1],max_dir[i/2],layer)
                                    if next_point : 
                                        masterpoint_n,layer_n,point_n = next_point
                                        print >>f,next_point
                                        self.gen.dic_group2info[abut_group[i/2]].availpoints[max_dir[(i+1)/2]][point_n][topo[i+1]].add(layer_n)
                                        self.dic_mastertile2location[mastertopo[i+1]][port[i+1]] = (masterpoint_n,layer_n,max_dir[(i+1)/2])

                            print >>f,'E01:Tile: %-15s Port: %-82s %-10s  %-10s %-10s %-10s' %(':'.join([mastertopo[i],topo[i]]),port[i],point,masterpoint[0],masterpoint[1],layer)
                        else:
                            if i%2 == 0 and port[i+1] in self.dic_mastertile2location[mastertopo[i+1]]:
                                masterpoint,layer,diruseless = self.dic_mastertile2location[mastertopo[i+1]][port[i+1]]
                                point = self.gen.dic_group2info[abut_group[i/2]].group2set_reversed[max_dir[i/2]][topo[i+1]].get(masterpoint,'-!-')
                                try:
                                    point_index = allow_point[i/2].index(point)
                                except ValueError:
                                    print >>f,'Error01: assigned port is conflict'
                                    if i%2 == 0: 
                                        next_point = self.find_nearest(f,point,abut_group[i/2],topo[i],max_dir[i/2],layer)
                                        if next_point :
                                            masterpoint_n,layer_n,point_n = next_point
                                            self.gen.dic_group2info[abut_group[i/2]].availpoints[max_dir[i/2]][point_n][topo[i]].add(layer_n)
                                            self.dic_mastertile2location[mastertopo[i]][port[i]] = (masterpoint_n,layer_n,max_dir[i/2])
                                            print >>f,'N01:Tile: %-15s Port: %-82s %-10s  %-10s %-10s %-10s' %(':'.join([mastertopo[i],topo[i]]),port[i],point_n,masterpoint_n[0],masterpoint_n[1],layer_n)
                                            continue
                            if point_index < len(allow_point[i/2]) - maxstep/3 -3:
                                point = allow_point[i/2][point_index]
                            else:
                                point_index_all[i] = 0
                                point_index = 0
                                point = allow_point[i/2][point_index]
                            point_old = point
                            point_index_old = point_index
                            flag_change_edge = True
                            if i%2 == 0 and port[i+1] not in self.dic_mastertile2location[mastertopo[i+1]]:
                                max_search_point = len(allow_point[i/2]) - 3
                                used_search_point = 1
                                banset = set(['Single',4]) #if track is allowed
                                avail =  set([self.dic_allowlayer[max_dir[i/2]] -1]) #track avail layer
                                threshold = 0
                                allow_track = set(range(self.dic_allowlayer[max_dir[i/2]]))
                                now_set_i = self.gen.dic_group2info[abut_group[i/2]].availpoints[max_dir[i/2]][point][topo[i]]
                                now_set_i_1 = self.gen.dic_group2info[abut_group[(i+1)/2]].availpoints[max_dir[(i+1)/2]][point][topo[i+1]]
                                while(now_set_i & banset or now_set_i_1 & banset or len(now_set_i & avail) != threshold or len(now_set_i_1 & avail) != threshold):
                                #while(now_set_i & banset or len(now_set_i_1 & avail) > 2 or len(now_set_i & avail) > 2):
                                    if used_search_point < max_search_point:
                                        point_index += 1
                                        #point_index = point_index%max_search_point
                                        ##change--11/26
                                        if point_index <= max_search_point:
                                            point_index = point_index%max_search_point
                                        else :
                                            point_index = max_search_point
                                        used_search_point += 1
                                    elif flag_change_edge:
                                        other_dir = (max_dir[i/2]+1)%2
                                        if other_dir in self.gen.dic_group2info[abut_group[i/2]].group2set_reversed and self.gen.dic_group2info[abut_group[i/2]].group2set_reversed[other_dir].keys():
                                            max_dir[i/2] = other_dir
                                            abut_set0 = set(self.gen.dic_group2info[abut_group[i/2]].availpoints[other_dir])
                                            sort_dir =  False if  allow_point[i/2][-1] - allow_point[i/2][0] > 0 else True
                                            allow_point[i/2] = tuple(sorted(abut_set0,reverse = sort_dir))
                                            max_search_point = len(allow_point[i/2]) - 3
                                            point_index = 0
                                        flag_change_edge = False
                                    else:
                                        if len(allow_track) == self.dic_allowlayer[max_dir[i/2]]:
                                            sort_dir =  False if  allow_point[i/2][-1] - allow_point[i/2][0] > 0 else True
                                            group2loc = self.gen.dic_group2info[abut_group[i/2]].group2loc[topo[i]]
                                            abut_set0 = set(self.gen.dic_group2info[abut_group[i/2]].availpoints[max_dir[i/2]])
                                            abut_set = abut_set0 & set(dic_topo2reuseedge[topo].get(mastertopo[i],{}).get(group2loc,set()))
                                            if abut_set:
                                                abut_set = abut_set|set(allow_point[i/2])
                                                a,b,c,d,e = max(abut_set),min(abut_set),max(allow_point[i/2]),min(allow_point[i/2]),len(allow_point[i/2])
                                                if a == c and b == d:
                                                    allow_point[i/2] = tuple(sorted(abut_set0,reverse = sort_dir))
                                                    print >>f,"Expand05: using all available points"
                                                else:
                                                    print >>f,"Expand05: new:",abut_group[i/2],a,b,'old:',c,d,e
                                                    allow_point[i/2] = tuple(sorted(abut_set,reverse = sort_dir))
                                            else:
                                                print >>f,"Expand05: using all available points"
                                                allow_point[i/2] = tuple(sorted(abut_set0,reverse = sort_dir))
                                            max_search_point = len(allow_point[i/2]) - 3
                                            allow_track.add('Change_side')
                                        else:
                                            if 'Change_side' in allow_track: allow_track.discard('Change_side')
                                            if allow_track:
                                                avail = set(range(self.dic_allowlayer[max_dir[i/2]]))
                                                banset = set()
                                                threshold = self.dic_allowlayer[max_dir[i/2]] - len(allow_track)
                                                allow_track.pop()
                                                block = set()
                                            else:
                                                break
                                        used_search_point = 1
                                    point = allow_point[i/2][point_index]
                                    now_set_i = self.gen.dic_group2info[abut_group[i/2]].availpoints[max_dir[i/2]][point][topo[i]]
                                    now_set_i_1 = self.gen.dic_group2info[abut_group[(i+1)/2]].availpoints[max_dir[(i+1)/2]][point][topo[i+1]]
                                if used_search_point == max_search_point:
                                    print >>f,'Failed'
                                    point_index = point_index_old
                                    point = allow_point[i/2][0]
                                    #kk changed for test
                                    #point = point_old
                                else:
                                    point = allow_point[i/2][point_index]
                                if i < len(point_index_all)- 1: point_index_all[i+1] = point_index
                            #print group
                            #print point
                            #print self.gen.dic_group2info[abut_group[i/2]]
                            now_set = self.gen.dic_group2info[abut_group[i/2]].availpoints[max_dir[i/2]][point][topo[i]]
                            now_set_r = now_set - block_golden
                            #print >>f,now_set_i,now_set_i_1,point_index_old,point_index,block,now_set,now_set_r
                            #if 4 in now_set: block = set([3])
                            while (layer in now_set or now_set & block or len(now_set_r) >= limit ):

                                if point_index >= len(allow_point[i/2]) - maxstep/3 -3:
                                    if dic_index2loop[i] == 5:
                                        print >>f,'C02:Port: %s has no track to be placed' % port[i],topo[i],allow_point[i/2][0],allow_point[i/2][-1]
                                        valid = False
                                        #self.dic_feed2portloc[topo][net_name].append(port[i])
                                        masterpoint = self.gen.dic_group2info[abut_group[i/2]].group2set[max_dir[i/2]][topo[i]][allow_point[i/2][0]]
                                        break
                                    elif dic_index2loop[i] == 0:
                                        print >>f,'#Port: %s has no golden track to be placed, expand edge' % port[i]
                                        sort_dir =  False if  allow_point[i/2][-1] - allow_point[i/2][0] > 0 else True
                                        group2loc = self.gen.dic_group2info[abut_group[i/2]].group2loc[topo[i]]
                                        abut_set0 = set(self.gen.dic_group2info[abut_group[i/2]].availpoints[max_dir[i/2]])
                                        abut_set = abut_set0 & set(dic_topo2reuseedge[topo].get(mastertopo[i],{}).get(group2loc,set()))
                                        if abut_set:
                                            abut_set = abut_set|set(allow_point[i/2])
                                            a,b,c,d,e = max(abut_set),min(abut_set),max(allow_point[i/2]),min(allow_point[i/2]),len(allow_point[i/2])
                                            if a == c and b == d:
                                                allow_point[i/2] = tuple(sorted(abut_set0,reverse = sort_dir))
                                                print >>f,"Expand04: using all available points"
                                            else:
                                                print >>f,"Expand04: new:",abut_group[i/2],a,b,'old:',c,d,e
                                                allow_point[i/2] = tuple(sorted(abut_set,reverse = sort_dir))
                                        else:
                                            print >>f,"Expand04: using all available points"
                                            allow_point[i/2] = tuple(sorted(abut_set0,reverse = sort_dir))
                                        point_index = allow_point[i/2].index(point)
                                    elif dic_index2loop[i] == 1:
                                        point_index == 1
                                    elif dic_index2loop[i] >= 2:
                                        #EX: if dic_index2loop[i] == 2: set(range(2)) == set([0,1]), mean
                                        block =  set() 
                                        limit = dic_index2loop[i] - 1
                                        point_index = point_index_all[i]
                                        if point_index >= len(allow_point[i/2]) - maxstep/3 -3:
                                            point_index = 0
                                    dic_index2loop[i] += 1
                                    point = allow_point[i/2][point_index]
                                    now_set = self.gen.dic_group2info[abut_group[i/2]].availpoints[max_dir[i/2]][point][topo[i]]
                                    now_set_r = now_set - block_golden
                                    layer = 0
                                    continue

                                if len(now_set_r) >= self.dic_allowlayer[max_dir[i/2]] or now_set & block:
                                    point_index += 1
                                    point = allow_point[i/2][point_index]
                                    now_set = self.gen.dic_group2info[abut_group[i/2]].availpoints[max_dir[i/2]][point][topo[i]]
                                    now_set_r = now_set - block_golden
                                    layer = 0
                                else:
                                    if layer/(self.dic_allowlayer[max_dir[i/2]] - 1):
                                        point_index += 1
                                        point = allow_point[i/2][point_index]
                                        now_set = self.gen.dic_group2info[abut_group[i/2]].availpoints[max_dir[i/2]][point][topo[i]]
                                        now_set_r = now_set - block_golden
                                    layer = (layer+1)%self.dic_allowlayer[max_dir[i/2]]
                            if valid:        
                                temp_step =  0 if i == 0 else dic_step.get(topo[i],0)
                                tmp_layer = layer
                                tmp_point_index = point_index
                                
                                self.gen.dic_group2info[abut_group[i/2]].availpoints[max_dir[i/2]][point][topo[i]].add(tmp_layer)
                                masterpoint = self.gen.dic_group2info[abut_group[i/2]].group2set[max_dir[i/2]][topo[i]][point]
                                self.dic_mastertile2location[mastertopo[i]][port[i]] = (masterpoint,tmp_layer,max_dir[i/2])
                                self.dic_mastertile2location_net[mastertopo[i]][port[i]] = (masterpoint,tmp_layer,max_dir[i/2])
                                self.dic_mastertile2usedlocation[mastertopo[i]][(masterpoint,tmp_layer)] = ''
                                dic_master2point[mastertopo[i]] = (masterpoint,tmp_layer)
                                #self.dic_feed2portloc[topo][net_name].append(masterpoint)
                                print >>f,'N01:Tile: %-15s Port: %-82s %-10s  %-10s %-10s %-10s |%-10s%-10s' %(':'.join([mastertopo[i],topo[i]]),port[i],point,masterpoint[0],masterpoint[1],tmp_layer,point_index_old,tmp_point_index),self.gen.dic_group2info[abut_group[i/2]].availpoints[max_dir[i/2]][point][topo[i]]
                            else:
                                self.dic_mastertile2constraintlocation[mastertopo[i]][port[i]] = self.dic_group2side[abut_group[i/2]][topo[i]]
                        point_index_all[i] = point_index
                        layer_all[i] = layer
                        if i < len(point_index_all)- 1 and point_index > point_index_all[i+1] and max_dir[i/2] == max_dir[(i+1)/2]:
                            point_index_all[i+1] = point_index
                            layer_all[i+1] = layer
                        if i%2 == 1 and point_index_all[i-1] < point_index_all[i]:
                            point_index_all[i-1] = point_index
                            layer_all[i-1] = layer
                    print >>f,'Old point_index,layer',point_index_all,layer_all
                    
                    while(step):
                        step -= 1
                        for j in range(len(layer_all)):
                            if point_index_all[j]+step < len(allow_point[j/2]):
                                point = allow_point[j/2][point_index_all[j]+step]
                                masterpoint = self.gen.dic_group2info[abut_group[j/2]].group2set[max_dir[j/2]][topo[j]][point]
                                self.dic_mastertile2skiplocation[mastertopo[j]][masterpoint] = ''
                            if  layer_all[j] <=  self.dic_allowlayer[max_dir[j/2]] -2 :
                                layer_all[j]  += 1
                            elif layer_all[j] == self.dic_allowlayer[max_dir[j/2]] -1:
                                layer_all[j] = 0
                                point_index_all[j] += 2

                    for id__ in range(len(point_index_all)):
                        if point_index_all[dic_tile2id[id__]] > point_index_all[id__]:
                            point_index_all[id__] = point_index_all[dic_tile2id[id__]]
                            layer_all[id__] = layer_all[dic_tile2id[id__]]
                    print >>f,'New point_index,layer',step,point_index_all,layer_all
                    #for j in range(len(abut_group)):
                    #    group = abut_group[j]
                    #    self.update_net_avail(max_dir[j],group,group[0])
                    #    self.update_net_avail(max_dir[j],group,group[1])
        f.close()

    def find_nearest(self,f,point,group,tile,max_dir,layer):
        group2loc = self.gen.dic_group2info[group].group2loc[tile]
        if not  hasattr(self.gen.dic_group2info[group],'sorted_points'):
            self.gen.dic_group2info[group].sorted_points = sorted(self.gen.dic_group2info[group].availpoints[max_dir])
            self.gen.dic_group2info[group].length = len(self.gen.dic_group2info[group].sorted_points)
        allow_point = self.gen.dic_group2info[group].sorted_points
        max_search_point = self.gen.dic_group2info[group].length
        Fail = False
        try:
            point_index = allow_point.index(point)
            print >>f,group,max_dir,point,tile
            now_set  = self.gen.dic_group2info[group].availpoints[max_dir][point][tile]
            print >>f,now_set,layer
            shift = 2
            used_search_point = 0
            while(layer in now_set):
                if layer < 2:
                    layer += 1
                    continue
                else:
                    point_index  =  (shift%2*2 -1)*shift/2 + point_index
                    if point_index >= 0 and point_index < max_search_point:
                        used_search_point += 1
                    else:
                        shift += 1
                        if used_search_point >= max_search_point:
                            Fail = True
                            break
                        continue
                    shift += 1
                    point = allow_point[point_index]
                    now_set = self.gen.dic_group2info[group].availpoints[max_dir][point][tile]
                    layer = 0
            if Fail == False:
                masterpoint  = self.gen.dic_group2info[group].group2set[max_dir][tile][point]
                return masterpoint,layer,point
            else:
                pass
        except ValueError:
            Fail = True
        if Fail:
            return False            
    


        
    def write_tcl(self):
        '''
            write port location into ICC2 format
        '''
        self.dic_master2clockport = defaultdict(list)
        for clockport in self.clockport.split():
            for path in glob.glob(clockport):
                master = path.split('/')[-1].split('.',1)[0]
                self.dic_master2clockport[master].append('source '+ path)
        with mkdir('port_location.pkl',mode='wb',type='data') as f:
            pickle.dump(self.dic_mastertile2location,f)

        numberofmaster = masterwithports = 0           
        for mastertile in self.shape.dic_master2inst:
            numberofmaster += 1
            with mkdir('placecollapsepins/%s.tcl' % mastertile , type = 'data') as f:
                if mastertile in self.dic_mastertile2constraintlocation:
                    for port in self.dic_mastertile2constraintlocation[mastertile]:
                        if port not in self.dic_mastertile2location[mastertile]:
                            loc = self.dic_mastertile2constraintlocation[mastertile][port]
                            print >>f, "set_individual_pin_constraints -ports %s -side { %s } " %( port, ' '.join([str(i) for i in loc]))
                if mastertile in self.dic_mastertile2location:
                    masterwithports += 1
                    for port in self.dic_mastertile2location[mastertile]:
                        if "HACKPP_" in port: continue
                        loc,layer,dir = self.dic_mastertile2location[mastertile][port]
                        #comment: below errors because of LAYERINDEX without M12:3 
                        #print dir,"aa",layer
                        layer = dic_dir2metal[dir][layer]
                        lbx = float(loc[0])
                        lby = float(loc[1])
                        rtx = float(loc[0])
                        rty = float(loc[1])
                        if self.dic_metal_dir[layer] == 0:
                            lbx = float(loc[0]) - 400
                            lby = float(loc[1]) - self.dic_width[layer]
                            rtx = float(loc[0]) + 400
                            rty = float(loc[1]) + self.dic_width[layer]
                            
                        else:
                            lbx = float(loc[0]) - self.dic_width[layer]
                            lby = float(loc[1]) - 400
                            rtx = float(loc[0]) + self.dic_width[layer]
                            rty = float(loc[1]) + 400
                        print >>f, 'fastRePlacePin %s {{%.4f %.4f} {%.4f %.4f}} %s' %(port,float(lbx)/2000,float(lby)/2000,float(rtx)/2000,float(rty)/2000, layer)
                        #print >>f, "set_individual_pin_constraints -ports %s -location { %.3f %.3f } -allowed_layers %s" %( port, float(loc[0])/2000, float(loc[1])/2000, layer)
                if mastertile in self.dic_master2clockport:
                    print >>f,'#Following constraints coming from oclk team...'
                    for cmd in self.dic_master2clockport[mastertile]:
                        print >>f,cmd
        
        print 'Info: %d/%d' %(masterwithports,numberofmaster)

    def write_report(self):    
        '''
            A !!!
        '''
        db = {}
        db['abut'] = self.dic_abut2portloc
        db['feed'] = self.dic_feed2portloc
        with mkdir('portloc.pkl', mode = 'wb',type = 'data') as file:
            pickle.dump(db,file)
    def plot(self):
        from matplotlib.path import Path
        from matplotlib.patches import PathPatch
        import matplotlib.pyplot as plt
        from matplotlib.lines import Line2D
        from matplotlib import colors
        fig,ax = plt.subplots()
        for inst in self.shape.dic_tiles:
            if self.shape.dic_tiles[inst].inst_poly.shape[0] == 1: continue
            tmp = np.row_stack((self.shape.dic_tiles[inst].inst_poly,np.array(self.shape.dic_tiles[inst].inst_poly[0])))
            vertices = np.array(tmp ,float)
            codes = [Path.MOVETO] + [Path.LINETO]*(self.shape.dic_tiles[inst].inst_poly.shape[0]-1) + [Path.CLOSEPOLY]
            path = Path(vertices, codes) 
            edgecolor = 'black' 
           
            facecolor = self.shape.dic_tiles[inst].tile_master.color 
            if inst == str(self.info["CHIPNAME"]):
                pathpatch = PathPatch(path,facecolor='None' ,edgecolor=edgecolor)
            else:
                pathpatch = PathPatch(path,facecolor=facecolor ,edgecolor=edgecolor)
            a,b = self.shape.dic_tiles[inst].inst_poly[0]
            #plt.text(a,b, inst, dict(size=15))
            ax.add_patch(pathpatch)
        dic_color = {}
        for mastergroup in self.dic_feedports:
            dic_color[tuple(sorted(list(mastergroup)))] = 'red'
            dic_color[tuple(sorted(list(mastergroup),reverse=True))] = 'blue'
            for net in self.dic_feedports[mastergroup]:
                location = []
                for pin in self.dic_feedports[mastergroup][net]:
                    tile,port = pin.split('/')
                    master = self.shape.dic_inst2master[tile]
                    if port in self.dic_mastertile2location[master]:
                        loc,layer,dir = self.dic_mastertile2location[master][port] 
                        loc = list(loc)
                        loc[0] += layer*10
                        loc[1] += layer*10
                        chip_location = self.shape.master2inst(master,[loc])[tile][0]
                    location.append(chip_location)
                    (x,y) = zip(*location)
                    ax.add_line(Line2D(x,y,linewidth=1,color=dic_color[mastergroup]))
        ax.autoscale_view()
        plt.show()
    def assign_misalign_pins(self):
        '''
            Try to align long net pins as close as possible
        '''
        pass
        
if __name__ == '__main__':
    commandLine, options, args = parseOptions(globals())
    config = getParams(options.config)
    reuse = Placecollapsepins(config)
    reuse.classify_ports()
    reuse.special_assignment(test = False)
    reuse.preassignpins()
    reuse.placeabutports(specify = True)
    reuse.placefeedports()
    reuse.placeabutports()
    #reuse.plot()
    reuse.write_tcl()
    #reuse.write_report()

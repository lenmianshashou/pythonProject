#!/tool/aticad/1.0/platform/RH6/bin/python

'''
     Contact: Pengpeng Jiang, 03A312 (Shanghai - Derek Cheng), EXT
     Date: 02/28/2018
     Version:0.62
'''
#########################
from collections import defaultdict
import os,logging,re
import cPickle as pickle
from operator import itemgetter
import copy
from optparse import *

#########################
import getshape
from mkdir import *
import fileparser
import logging_amd
from daedalus import *
from getParams import *
dic_dir2metal = {}

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
    def __init__(self):
        
        #self.params = getParams(params = './scripts/pinassign_tahiti_ca_atp.cfg')
        #self.info = self.params.jsonconf['collapse']
        self.info = config.jsonconf['collapse']
        self.layer_info()
        self.get_waivedgroup()
        self.shape = getshape.getshape()
        self.shape.parsedef(file=self.info["DEF"],read_from_pkl = self.info["DEF_READ_FROM_PKL"],pkl_name = 'getshape_collapse.pkl',chipname = str(self.info["CHIPNAME"]),track_valid = eval(self.info['VALIDTRACK']))
        self.shape.getReuse()
        self.shape.getabuttile()
        self.shape.sortabutlistbycommonedge()
        self.shape.filter_edge()
        self.get_pregrouptopo()
        self.feedconn = fileparser.parser_feedconn(file=self.info["FEEDCONN"],file1=self.info["INITCONN"],read_from_pkl = self.info["FEEDCONN_READ_FROM_PKL"])
        self.netconn = fileparser.parser_netconn2(file=self.info["NETCONN"],read_from_pkl = self.info["NETCONN_READ_FROM_PKL"])
        self.readbkg = getshape.get_blockage(self.shape,tune = self.info["BKG"])
        #self.readbkg.plot()
        #self.readbkg.plot_edge()

        self.gen = Portgenerator(self.shape,chipname = str(self.info["CHIPNAME"]),dic_metal_dir = self.dic_metal_dir)
        self.gen.generatepoints()
        self.gen.pre_block_track(dic_group_preassign = {})
        #get reuse tile list
        self.dic_reuse = {}
        for master in self.shape.dic_master2inst:
            if len(self.shape.dic_master2inst[master]) > 1:
                for tile in self.shape.dic_master2inst[master]:
                    self.dic_reuse[tile] = ''

        self.username =  os.popen("who | cut -d' ' -f1 | sort | uniq").readlines()[0].strip()
        self.log = logging_amd.logging_amd(file_name = 'placecollapsepins.log')

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
        track = {'X':1,'Y':0}
        self.dic_allowlayer = eval(self.info['ALLOWLAYER'])
        self.dic_allowlayer[0] = len(self.dic_allowlayer['Y'])
        self.dic_allowlayer[1] = len(self.dic_allowlayer['X'])
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
                    driv_tile = '/'.join(driver.split('/',2)[0:-1])
                    #driv_tile = self.netconn.dic_net2driv[net][0].split('/',2)[-2]
                    load_tile = '/'.join(load.split('/',2)[0:-1])
                    #load_tile = self.netconn.dic_net2load[net][0].split('/',2)[-2]
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
            elif net in self.feedconn.dic_net2feed:
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
                if driv_tile in self.shape.dic_inst2master and load_tile in self.shape.dic_inst2master:
                    self.dic_feedports[(driv_tile,load_tile)][net] = self.feedconn.dic_net2feed[net]
                elif driv_tile not in self.shape.dic_inst2master and load_tile not in self.shape.dic_inst2master:
                    
                    self.dic_bufferports[(self.netconn.dic_net2driv[net][0],self.netconn.dic_net2load[net][0])][net] = self.feedconn.dic_net2feed[net]
                    driv_tile = '/'.join(self.feedconn.dic_net2feed[net][2].split('/',2)[0:-1])
                    load_tile = '/'.join(self.feedconn.dic_net2feed[net][-3].split('/',2)[0:-1])
                    if len(self.feedconn.dic_net2feed[net]) > 6:
                        self.dic_feedports[(driv_tile,load_tile)][net] = self.feedconn.dic_net2feed[net][2:-2]
                    else:
                        self.dic_abuttingports[(driv_tile,load_tile)][net] = self.feedconn.dic_net2feed[net][2:-2]
                elif driv_tile not in self.shape.dic_inst2master:
                    self.dic_bufferports[(self.netconn.dic_net2driv[net][0],load_tile)][net] = self.feedconn.dic_net2feed[net]
                    driv_tile = '/'.join(self.feedconn.dic_net2feed[net][2].split('/',2)[0:-1])
                    load_tile = '/'.join(self.feedconn.dic_net2feed[net][-1].split('/',2)[0:-1])
                    if len(self.feedconn.dic_net2feed[net]) > 4:
                        self.dic_feedports[(driv_tile,load_tile)][net] = self.feedconn.dic_net2feed[net][2:]
                    else:
                        self.dic_abuttingports[(driv_tile,load_tile)][net] = self.feedconn.dic_net2feed[net][2:]
                elif load_tile not in self.shape.dic_inst2master:
                    self.dic_bufferports[(driv_tile,self.netconn.dic_net2load[net][0])][net] = self.feedconn.dic_net2feed[net]
                    driv_tile = '/'.join(self.feedconn.dic_net2feed[net][0].split('/',2)[0:-1])
                    load_tile = '/'.join(self.feedconn.dic_net2feed[net][-3].split('/',2)[0:-1])
                    if len(self.feedconn.dic_net2feed[net]) > 4:
                        self.dic_feedports[(driv_tile,load_tile)][net] = self.feedconn.dic_net2feed[net][0:-2]
                    else:
                        self.dic_abuttingports[(driv_tile,load_tile)][net] = self.feedconn.dic_net2feed[net][0:-2]
        ##for feed case:
        self.dic_group2topo = defaultdict(dict)
        self.dic_topo2port = defaultdict(dict)
        self.dic_mastergroup2group = defaultdict(dict)
        for group in self.dic_feedports:
            for net in self.dic_feedports[group]:
                topo = []
                port = []
                for p in self.dic_feedports[group][net]:
                    tmp =  p.split('/')
                    tilename = '/'.join(tmp[0:-1])
                    if tilename not in self.shape.dic_inst2master: continue
                    topo.append(tilename)
                    port.append(tmp[-1])
                self.dic_topo2port[tuple(topo)][tuple(port)] = ''
                self.dic_group2topo[group][tuple(topo)] = ''
        for group in    self.dic_abuttingports:
            ##comment:below errors because of chip.def without component
            mastergroup = tuple([self.shape.dic_inst2master[i] for i in group])
            self.dic_mastergroup2group[mastergroup][group] = ''
        
        with mkdir('placecollapsepins/classify_ports.rpt') as f:
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
            print >>f,'#dic_group2topo'
            for i in self.dic_group2topo: 
                print >>f, i
                for j in self.dic_group2topo[i]:
                    print >>f,j

        logging.info('Ending classify ports.')

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
        #print self.shape.dic_inst2master
        #print self.dic_feedports
        for group in self.dic_feedports:
            driv, load =  group
            dic_tmp[(self.shape.dic_inst2master[driv],self.shape.dic_inst2master[load])][group] = ''
        for group in dic_tmp:
            if len(dic_tmp[group]) > 1:
                self.dic_groupdriv[group] = dic_tmp[group]
                dic_usedgroup.update(dic_tmp[group])
        #2
        self.dic_groupother = defaultdict(dict)
        for group in self.dic_feedports:
            if group not in dic_usedgroup:
                self.dic_groupother[(self.shape.dic_inst2master[group[0]],self.shape.dic_inst2master[group[1]])][group] = ''
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

    def getrelation(self):
        '''
            get feedthru group topo path
            Function:
            from: bottleneck alogrithm -> abutgroup
            from: self.dic_abutgroup2topo -> topo
            from: self.dic_topo2group -> group
            from: self.dic_group2master -> master group
            Ports would be placed by master group!!
        '''
        self.dic_net2topo= defaultdict(list) #net->[tile0,tile1,...,tileN]
        self.dic_net2port = defaultdict(list) #net->[port0,port1,...,portN]
        self.dic_abutgroup2topo = defaultdict(dict)


        self.dic_topo2group = {}  #topo path -> [start,end] -> ''
        #self.dic_group2topo = defaultdict(dict)  #[start,end] -> topo path -> ''

        self.dic_group2master = {}

        for net in self.feedconn.dic_net2feed:
            for value in self.feedconn.dic_net2feed[net]:
                tmp = value.split('/')
                tmp0 = '/'.join(tmp[0:-1])
                tmp1 = '/'.join(tmp[-1])
                if tmp0 in self.shape.dic_inst2master:
                    tile = tmp0
                    port = tmp1
                else:
                    tile = port = value
                self.dic_net2topo[net].append(tile) 
                self.dic_net2port[net].append(port)
            topo = tuple(self.dic_net2topo[net])
            group = (topo[0],topo[-1])
            for i in range(0,len(topo)-1,2):
                self.dic_abutgroup2topo[(topo[i],topo[i+1])][topo] = ''
                self.dic_abutgroup2topo[(topo[i+1],topo[i])][topo] = ''
            self.dic_topo2group[topo] = group
            #self.dic_group2topo[group][topo] = ''

        for group in self.dic_groupdriv:
            for subgroup in self.dic_groupdriv[group]:
                self.dic_group2master[subgroup] = group
        for group in self.dic_groupother:
            for subgroup in self.dic_groupother[group]:
                self.dic_group2master[subgroup] = group
        dic_relation = {}
        dic_relation['dic_topo2group'] = self.dic_topo2group
        dic_relation['dic_abutgroup2topo'] = self.dic_abutgroup2topo
        dic_relation['dic_group2master'] = self.dic_group2master
        with mkdir('relation.pkl',mode='wb',type='data') as f:
            pickle.dump(dic_relation,f)
        with mkdir('placecollapsepins/getrelation.rpt') as f:
            print >>f,'#group -> topo'
            for topo in self.dic_topo2group:
                print >>f, self.dic_topo2group[topo]
                print >>f, topo,'\n'
            print >>f,'#abut group -> topo'
            for group in self.dic_abutgroup2topo:
                for topo in self.dic_abutgroup2topo[group]:
                    print >>f, group
                    print >>f, topo,'\n'
            print >>f,'#master group -> group'
            for group in self.dic_group2master:
                print >>f, group,self.dic_group2master[group]
        print "Ending get relationship"
        #######
    def getmastergroup(self,abutgroup):
        '''
            Function:
            from: bottleneck alogrithm -> abutgroup
            from: self.dic_abutgroup2topo -> topo
            from: self.dic_topo2group -> group
            from: self.dic_group2master -> master group

        '''
        topo = self.dic_abutgroup2topo[abutgroup]
        group = [self.dic_topo2group[i] for i in topo]
        mastergroups = [self.dic_group2master[i] for i in group if i in self.dic_group2master ]
        
        return mastergroups

    def mergeport(self):
        '''
        '''
        self.dic_mastergroup2reuserepeat = {}
        for mastergroup in self.dic_groupdriv:
            groups = self.dic_groupdriv[mastergroup].keys()
            #case1: reuse tile -> *
            reuserepeat = 1
            if groups[0][0] in self.dic_reuse:
                for group in groups:
                    for topo in self.dic_group2topo[group]:
                        tmp = 1
                        for i in range(1,len(topo),2):
                            if self.shape.dic_inst2master[topo[i]] == self.shape.dic_inst2master[topo[0]]:
                                tmp += 1
                            else:
                                if tmp > reuserepeat: 
                                    flagtopo = topo
                                    reuserepeat = tmp
                                    self.dic_mastergroup2reuserepeat[mastergroup] = reuserepeat
                                break
            elif groups[0][-1] in self.dic_reuse:
                for group in groups:
                    for topo in self.dic_group2topo[group]:
                        tmp = 1
                        for i in range(-2,-len(topo)-1,-2):
                            if self.shape.dic_inst2master[topo[i]] == self.shape.dic_inst2master[topo[-1]]:
                                tmp += 1
                            else:
                                if tmp > reuserepeat: 
                                    flagtopo = topo
                                    reuserepeat = tmp
                                    self.dic_mastergroup2reuserepeat[mastergroup] = reuserepeat
                                break 
            
        with mkdir('placecollapsepins/mergeport.rpt') as f:
            for mastergroup in self.dic_mastergroup2reuserepeat:
                print >>f,mastergroup,self.dic_mastergroup2reuserepeat[mastergroup]
                for group in  self.dic_groupdriv[mastergroup]:
                    print >>f,group
                    print >>f, self.dic_group2topo[group]
    
    def get_waivedgroup(self,file='getshape/wavie_union_group.tune'):              
        '''
            Get master group which do not need to be process!
        '''
        self.dic_waviegroup = {}
        with mkdir(file,mode = 'r+', type = 'tunes') as f:
            pt = re.compile(r'(\S+) (\S+)')
            for line in f:
                mt = pt.search(line)
                if mt:
                    self.dic_waviegroup[mt.groups()] = ''
    def get_pregrouptopo(self):
        self.dic_mastergroup2usertopo  = defaultdict(dict)
        self.dic_usr2group = defaultdict(dict)
        with  mkdir('placecollapsepins/group_topo.tune',type = 'tunes',mode = 'r+') as f:
            for line in f:
                tmp = line.split()
                if tmp == []: continue
                mastergroup = (self.shape.dic_inst2master[tmp[1]],self.shape.dic_inst2master[tmp[-1]])
                mastergroup_r = (self.shape.dic_inst2master[tmp[-1]],self.shape.dic_inst2master[tmp[1]])
                self.dic_mastergroup2usertopo[mastergroup][tmp[0]] = []
                self.dic_mastergroup2usertopo[mastergroup_r][tmp[0]] = []
                self.dic_usr2group[tmp[0]][tuple(tmp[1:])] = ''
                self.dic_usr2group[tmp[0]][tuple(reversed(tmp[1:]))] = ''
        for mg in self.dic_mastergroup2usertopo:
            for name in self.dic_mastergroup2usertopo[mg]:
                self.dic_mastergroup2usertopo[mg][name] = self.dic_usr2group[name].keys()

    def get_reverse(self):
        '''
        '''
        self.dic_reverse_value = defaultdict(dict)
        with mkdir('placecollapsepins/reverse.tune',type = 'tunes',mode = 'r+') as f:
            for line in f:
                if '#' in line: continue
                tmp = line.strip().split()
                reverse_tmp = tuple(tmp[0:-1])
                value_tmp = tmp[-1]
                self.dic_reverse_value[reverse_tmp]= value_tmp

    def placeuniqports(self):
        '''
            We try to place ports in following order:
                No.1 feed ports
                No.2 buffer ports
                No.3 abutting ports
                No.4 other ports
        '''
        ID = 0
        self.get_reverse()
        self.dic_topo2reuseedge = defaultdict(dict)
        self.dic_mastertile2location = defaultdict(dict)
        self.totaltopo = {}
        dic_placedmastergroup = {}
        dic_usedbottleneck = {}
        dic_relaxtion = {0:'Y',1:'X'}
        grouporder = []
        group_unprocess= []
        setA = set(self.dic_groupother.keys()) | set(self.dic_groupdriv.keys())
        numberofmaster = len(setA)
        logging.info('Total number of mastergroup: %d' % numberofmaster)
        file = mkdir_open('placecollapsepins/placeuniqports.rpt')
        tuple_group2info = sorted(self.gen.dic_group2info.keys(),key = lambda group: len(self.gen.dic_group2info[group].group2set))
        while( len(dic_placedmastergroup) != numberofmaster):
            for i in tuple_group2info:
                if i not in dic_usedbottleneck:
                    abutgroup = i 
                    dic_usedbottleneck[i] = ''
                    break
            mastergroups = [group for group in self.getmastergroup(abutgroup) if group not in dic_placedmastergroup]
            if len(mastergroups) == 0 and i == tuple_group2info[-1]: 
                print 'Total %d master group. only %d processed' %(len(setA),len(dic_placedmastergroup))
                remainingGroup = setA - set(dic_placedmastergroup)
                print 'Folloiwng group cannot be processed:',remainingGroup
                for g in remainingGroup:
                    dic_placedmastergroup[g] = 'manual'
                    mastergroups = remainingGroup
            #print >>file,'#abutgroup',abutgroup
            #####fetch unplaced master groups :df_tcdx_ch0_t_br df_tcdx21_t
            else:
                dic_unplacedmaster = {}
                for g in mastergroups:
                    dic_unplacedmaster[g] = ''
                mastergroups = set(dic_unplacedmaster) - (set(dic_unplacedmaster)&set(dic_placedmastergroup))
                for g in mastergroups:
                    dic_placedmastergroup[g] = ''
            #####end fetch unplaced master groups
            for mastergroup in mastergroups:
                ID += 1
                print '#',ID,numberofmaster,mastergroup
                print >>file,'#',mastergroup
                grouporder.append(mastergroup)
                dic_topolist = {} #dic_topolist: keys: topos of mastergroup
                
                #generate topo list of a mastergroup
                if mastergroup in self.dic_groupdriv:
                    for group in self.dic_groupdriv[mastergroup]:
                        dic_topolist.update(self.dic_group2topo[group])
                elif mastergroup in self.dic_groupother:
                    for group in self.dic_groupother[mastergroup]:
                        dic_topolist.update(self.dic_group2topo[group])
                dic_maxnets = defaultdict(int) #store net number of a master group
                for topo in dic_topolist:
                    tmp = len(self.dic_topo2port[topo])
                    dic_maxnets[topo] = tmp

                #1 intersection points between abutting edge of one topo
                topo_user = []
                if mastergroup in self.dic_mastergroup2usertopo:
                    for g in self.dic_mastergroup2usertopo[mastergroup]:
                        topo_user.extend(self.dic_mastergroup2usertopo[mastergroup][g])
                topo_other = set(dic_topolist) - set(topo_user)
                self.dic_mastergroup2usertopo[mastergroup]['Others'] = list(topo_other)
                for name in self.dic_mastergroup2usertopo[mastergroup]:
                    print >>file,'#Processing group:',mastergroup,name
                    topolist = self.dic_mastergroup2usertopo[mastergroup][name]
                    if topolist == []:
                        print >>file, 'Error: no topo list'
                        continue
                    dic_topo = defaultdict(dict) #dic_topo: keys: topo values: various information of topo
                    dic_reuse2group =  defaultdict(dict)
                    dic_inst2group =  defaultdict(dict)
                    dic_inst2group_orignal = defaultdict(dict)
                    dic_inst2commonpoint = defaultdict(dict)
                    dic_reuse2commonpoint = defaultdict(dict)

                    dic_reuse2group_abut =  defaultdict(dict)
                    for topo in topolist:
                        breakif = 0
                            
                        #value means number of inst orient
                        #if value > 0, we need to get union otherwise intersection
                        dic_instwithintopo = defaultdict(dict)
                        for t in topo:
                            if t not in self.shape.dic_inst2master:
                                breakif = 1
                                break
                            dic_instwithintopo[self.shape.dic_inst2master[t]][self.shape.dic_tiles[t].inst_orient] = ''         
                        if breakif:
                            continue
                            
                        flagpoint = {}
                        abut_group = []
                        max_dir = []
                        allow_point = []
                        dic_location = {}
                        stop = 0

                        if len(topo)%2:
                            if len(topo)%2:
                                print >>file, 'Error: Not normal topo with odd number',len(topo),topo
                            continue
                        
                        for i in range(len(topo)/2):
                            i *= 2
                            g = (topo[i], topo[i+1])
                            if g not in self.gen.dic_group2info:
                                logging.error('Group:%s not abutted in  TOPO:%s' % (' '.join(g),' '.join(topo)))
                                print >>file, 'Error00: Group:%s not abutted in  TOPO' % (' '.join(g)),topo
                                stop = 1
                                abut_group.append(g)
                                max_dir.append(0)
                                allow_point.append(set())
                                self.gen.dic_group2info[g] = type(' '.join(g),(),{'routedir':{0:0},
                                'max_dir':0,
                                'group2point':dict(),
                                'group2set':{0:{t:tuple() for t in g}},
                                'group2set_reversed':{0:{t:tuple() for t in g}},
                                'groupname':g,
                                'availpoints':{0:dict()},
                                'group2loc':{t:tuple() for t in g}
                                
                                })
                            else:   
                                dir = self.gen.dic_group2info[g].max_dir
                                abut_group.append(g)
                                max_dir.append(dir)
                                allow_point.append(set(self.gen.dic_group2info[g].availpoints[dir]))
                        if mastergroup in self.dic_waviegroup:
                            dic_topo[topo]['abut_group'] = abut_group
                            dic_topo[topo]['max_dir'] = max_dir
                            dic_topo[topo]['allow_point'] = allow_point
                            dic_topo[topo]['location'] = dic_location
                            continue
                        m = 0
                        start_tile,end_tile = topo[0],topo[-1]
                        st_master,et_master = self.shape.dic_inst2master[start_tile],self.shape.dic_inst2master[end_tile]
                        for g in self.dic_mastergroup2group.get((st_master,et_master),{}):
                            if g not in self.gen.dic_group2info: continue
                            for inst in g:
                                dir = self.gen.dic_group2info[g].max_dir
                                master = self.shape.dic_inst2master[inst]
                                tile_loc = self.gen.dic_group2info[g].group2loc[inst]
                                if inst in dic_inst2commonpoint and tile_loc in dic_inst2commonpoint[inst]:
                                    dic_inst2commonpoint[inst][tile_loc] |=   set(self.gen.dic_group2info[g].group2set_reversed[dir][inst])
                                else:
                                    dic_inst2commonpoint[inst][tile_loc] =  set(self.gen.dic_group2info[g].group2set_reversed[dir][inst])
                                if inst in dic_inst2group and tile_loc in dic_inst2group[inst]:
                                    dic_inst2group[inst][tile_loc] |=  set(self.gen.dic_group2info[g].group2set_reversed[dir][inst])
                                else:
                                    dic_inst2group[inst][tile_loc] =  set(self.gen.dic_group2info[g].group2set_reversed[dir][inst])
                        if len(topo) < 3: continue
                        for i in range(len(topo)):
                            inst = topo[i]
                            #if inst not in self.dic_reuse: continue
                            master = self.shape.dic_inst2master[inst]
                            tile_loc = self.gen.dic_group2info[abut_group[i/2]].group2loc[inst]
                            #print abut_group[i/2],inst,tile_loc
                            if inst in dic_inst2commonpoint and tile_loc in dic_inst2commonpoint[inst]:
                                dic_inst2commonpoint[inst][tile_loc] |=   set(self.gen.dic_group2info[abut_group[i/2]].group2set_reversed[max_dir[i/2]][inst])
                            else:
                                dic_inst2commonpoint[inst][tile_loc] =  set(self.gen.dic_group2info[abut_group[i/2]].group2set_reversed[max_dir[i/2]][inst])
                            
                         
                        for i in range(len(abut_group) - 1):
                            if max_dir[i] == max_dir[i+1]:
                                new_point = allow_point[i] & allow_point[i+1]
                                max_layer_num = self.dic_allowlayer[max_dir[i]]
                                if len(new_point) <= dic_maxnets[topo]/max_layer_num*2:
                                    flagpoint[i] = allow_point[i]
                                    new_point = allow_point[i+1]
                                else:
                                    allow_point[i] = new_point
                                    allow_point[i+1] = new_point
                            else:#if turn round
                                new_point = allow_point[i]
                                for j in range(i,m-1,-1):
                                    if j in flagpoint: new_point = flagpoint[j]
                                    allow_point[j] = new_point
                                    for (reusetile,insttile) in [(self.shape.dic_inst2master[tile],tile) for tile in abut_group[j] if tile in self.dic_reuse]:
                                        tile_loc = self.gen.dic_group2info[abut_group[j]].group2loc[insttile]
                                        if insttile in dic_inst2group and tile_loc in dic_inst2group[insttile]:
                                            dic_inst2group[insttile][tile_loc] |=  set(self.gen.dic_group2info[abut_group[j]].group2set[max_dir[j]][insttile][point] for point in new_point)
                                        else:
                                            dic_inst2group[insttile][tile_loc] =  set(self.gen.dic_group2info[abut_group[j]].group2set[max_dir[j]][insttile][point] for point in new_point)

                                m = i + 1
                                for (reusetile,insttile) in [(self.shape.dic_inst2master[tile],tile) for tile in abut_group[i+1] if tile in self.dic_reuse]:
                                    tile_loc = self.gen.dic_group2info[abut_group[i+1]].group2loc[insttile]
                                    if insttile in dic_inst2group and tile_loc in dic_inst2group[insttile]:
                                        dic_inst2group[insttile][tile_loc] |=  set(self.gen.dic_group2info[abut_group[i+1]].group2set[max_dir[i+1]][insttile][point] for point in allow_point[i+1])
                                    else:
                                        dic_inst2group[insttile][tile_loc] =  set(self.gen.dic_group2info[abut_group[i+1]].group2set[max_dir[i+1]][insttile][point] for point in allow_point[i+1] )
                                continue
                            for j in range(1+i,m-1,-1):
                                if j in flagpoint: 
                                    new_point = flagpoint[j]
                                allow_point[j] = new_point
                                for (reusetile,insttile) in [(self.shape.dic_inst2master[tile],tile) for tile in abut_group[j] if tile in self.dic_reuse]:
                                    tile_loc = self.gen.dic_group2info[abut_group[j]].group2loc[insttile]
                                    if insttile in dic_inst2group and tile_loc in dic_inst2group[insttile]:
                                        dic_inst2group[insttile][tile_loc] |=  set(self.gen.dic_group2info[abut_group[j]].group2set[max_dir[j]][insttile][point] for point in new_point)
                                    else:
                                        dic_inst2group[insttile][tile_loc] =  set(self.gen.dic_group2info[abut_group[j]].group2set[max_dir[j]][insttile][point] for point in new_point) 
                        dic_topo[topo]['abut_group'] = abut_group
                        dic_topo[topo]['max_dir'] = max_dir
                        dic_topo[topo]['allow_point'] = allow_point
                        dic_topo[topo]['location'] = dic_location

                    dic_skipgroup = {}    

                    for inst in dic_inst2commonpoint:
                        for tile_loc in dic_inst2commonpoint[inst]:
                            reusetile = self.shape.dic_inst2master[inst]
                            if len(dic_inst2commonpoint[inst][tile_loc]):
                                if reusetile in dic_reuse2commonpoint and tile_loc in dic_reuse2commonpoint[reusetile]:
                                    if dic_reuse2commonpoint[reusetile][tile_loc] & dic_inst2commonpoint[inst][tile_loc]:
                                        dic_reuse2commonpoint[reusetile][tile_loc] &= dic_inst2commonpoint[inst][tile_loc]
                                    else:
                                        dic_reuse2commonpoint[reusetile][tile_loc] |= dic_inst2commonpoint[inst][tile_loc]
                                else:
                                    dic_reuse2commonpoint[reusetile][tile_loc] = dic_inst2commonpoint[inst][tile_loc]
                    for inst in dic_inst2group:
                        for tile_loc in dic_inst2group[inst]:
                            reusetile = self.shape.dic_inst2master[inst]
                            print >>file,reusetile,inst,tile_loc,sorted(dic_inst2group[inst][tile_loc])
                            if len(dic_inst2group[inst][tile_loc]):
                                if reusetile in dic_reuse2group and tile_loc in dic_reuse2group[reusetile]:
                                    if dic_reuse2group[reusetile][tile_loc] & dic_inst2group[inst][tile_loc]:
                                        dic_reuse2group[reusetile][tile_loc] &= dic_inst2group[inst][tile_loc]
                                    else:
                                        dic_reuse2group[reusetile][tile_loc] = dic_reuse2commonpoint[reusetile][tile_loc]
                                        dic_skipgroup[inst] = ''
                                else:
                                    dic_reuse2group[reusetile][tile_loc] = dic_inst2group[inst][tile_loc]
                                print >>file,'#',reusetile,tile_loc,len(dic_reuse2group[reusetile][tile_loc])
                    for reusetile in dic_reuse2group:
                        for tile_loc in dic_reuse2group[reusetile]:
                            print >>file,reusetile,tile_loc
                            tmp = sorted(dic_reuse2group[reusetile][tile_loc],key = itemgetter(1))
                            if tmp:
                                print >>file, tmp[0],tmp[-1]
                    
                    #2 intersection between reuse tiles
                    for topo in dic_topo:
                        dic_topo2reuseedge_tmp = defaultdict(dict)
                        tracknum = len(dic_topo[topo]['allow_point'][0])
                        if tracknum  < dic_maxnets[topo]/3:
                            print >>file,'##topo',topo,tracknum,dic_maxnets[topo]
                        else:
                            print >>file,'#topo',topo,tracknum,dic_maxnets[topo]
                        print >>file,dic_topo[topo]['max_dir']
                        print >>file,[len(i) for i in  dic_topo[topo]['allow_point']]
                        
                        for i in range(len(dic_topo[topo]['abut_group'])):
                            group = dic_topo[topo]['abut_group'][i]
                            max_dir_index = dic_topo[topo]['max_dir'][i]
                            for inst in group :
                                master =  self.shape.dic_inst2master[inst]
                                if inst not in self.dic_reuse: continue
                                tile_loc = self.gen.dic_group2info[group].group2loc[inst]
                                if master in dic_reuse2group and tile_loc in dic_reuse2group[master]:
                                    b = set(self.gen.dic_group2info[group].group2set_reversed[max_dir_index][inst][p] for p in dic_reuse2group[master][tile_loc] if p in self.gen.dic_group2info[group].group2set_reversed[max_dir_index][inst])
                                    if master in dic_reuse2commonpoint and tile_loc in dic_reuse2commonpoint[master]:
                                        mg = [self.shape.dic_inst2master[g] for g in  group]
                                        lg = [self.gen.dic_group2info[group].group2loc[g] for g in  group]
                                        common = set(self.gen.dic_group2info[group].group2set_reversed[max_dir_index][inst][p] for p in dic_reuse2commonpoint[master][tile_loc] if p in self.gen.dic_group2info[group].group2set_reversed[max_dir_index][inst])
                                        dic_topo2reuseedge_tmp[mg[0]][lg[0]] =  common
                                        dic_topo2reuseedge_tmp[mg[1]][lg[1]] = common
                                        if common:
                                            print >>file,master,inst,tile_loc,len(common),max(common),min(common)
                                        else:
                                            print >>file, master,inst,tile_loc,len(common),len(dic_reuse2commonpoint[master][tile_loc])
                                    if dic_topo[topo]['allow_point'][i] & b:
                                        dic_topo[topo]['allow_point'][i] &= b
                                        print >>file,master, tile_loc,'00'
                                    else:
                                        point_tmp = set()
                                        print >>file,master, tile_loc,'01'
                                        for inst in group:
                                            if inst not in self.dic_reuse: continue
                                            master =  self.shape.dic_inst2master[inst]
                                            tile_loc = self.gen.dic_group2info[group].group2loc[inst]
                                            if master in dic_reuse2commonpoint and tile_loc in dic_reuse2commonpoint[master]:
                                                b = set(self.gen.dic_group2info[group].group2set_reversed[max_dir_index][inst][p] for p in dic_reuse2commonpoint[master][tile_loc] if p in self.gen.dic_group2info[group].group2set_reversed[max_dir_index][inst])
                                                if point_tmp : 
                                                    point_tmp &=  b 
                                                else:
                                                    point_tmp = b
                                                if point_tmp:
                                                    dic_topo[topo]['allow_point'][i] = copy.deepcopy(point_tmp)
                                                    print >>file,master,inst, tile_loc,'000',max(b),min(b)
                                                else:
                                                    dic_topo[topo]['allow_point'][i] = set(self.gen.dic_group2info[group].group2set[max_dir_index][inst])
                                                    print >>file,master,inst, tile_loc,'011'
                        self.dic_topo2reuseedge[topo] = dic_topo2reuseedge_tmp
                        print >>file,'S01:', [len(i) for i in  dic_topo[topo]['allow_point']]
                        m = 0
                        max_dir = dic_topo[topo]['max_dir']
                        allow_point = dic_topo[topo]['allow_point']
                        flagpoint = {}
                        for i in range(len(allow_point)-1):
                            if max_dir[i] == max_dir[i+1]:
                                group_ = dic_topo[topo]['abut_group']
                                if group_[0] not in dic_skipgroup and group_[1] not in dic_skipgroup:
                                    max_layer_num = self.dic_allowlayer[max_dir[i]]
                                    new_point = allow_point[i] & allow_point[i+1]
                                    if len(new_point) <= dic_maxnets[topo]/max_layer_num:
                                        flagpoint[i] = allow_point[i]
                                        new_point = allow_point[i+1]
                                        continue
                                    allow_point[i] = new_point
                                    allow_point[i+1] = new_point
                            else:#if turn round
                                new_point = allow_point[i]
                                for j in range(i,m-1,-1):
                                    if j in flagpoint: new_point = flagpoint[j]
                                    allow_point[j] = new_point
                                m = i + 1
                                continue
                            for j in range(i,m-1,-1):
                                if j in flagpoint: 
                                    new_point = flagpoint[j]
                                allow_point[j] = new_point
                        dic_topo[topo]['allow_point'] = allow_point
                    #transfer set to list database
                        tmp = [len(i) for i in  dic_topo[topo]['allow_point']]
                        if 0 in tmp:
                            print >>file,'Error:',tmp
                        else:
                            print >>file,tmp
                    for topo in dic_topo.keys():
                        ##print >>file,topo
                        flag = 0
                        for i in range(len(dic_topo[topo]['allow_point'])):
                            if len(dic_topo[topo]['allow_point'][i]) == 0:
                                flag = 1
                        if flag or len(dic_topo[topo]['max_dir']) == 0: 
                            group_unprocess.append(topo)
                            dic_topo.pop(topo)
                            print >>file,'Error02:',topo
                            continue

                        tile = topo[0]
                        maxdir = dic_topo[topo]['max_dir'][0]
                        orientation = self.shape.dic_tiles[tile].inst_orient
                        reuseID = 0
                        
                        for i in range(len(topo)):
                            tmp = topo[i]
                            if tmp in self.dic_reuse:
                                orientation = self.shape.dic_tiles[tmp].inst_orient
                                maxdir = dic_topo[topo]['max_dir'][i/2]
                                reuseID = i/2
                                break

                        if maxdir:
                            if orientation == 'FN' or orientation == 'S':
                                reverse_original = True
                            else:
                                reverse_original = False
                        else:
                            if orientation == 'FS' or orientation == 'S':
                                reverse_original = True
                            else:
                                reverse_original = False

                        if topo in self.dic_reverse_value :
                            if self.dic_reverse_value[topo] == 'True' : 
                                reverse_original = True
                            else :
                                reverse_original = False
                                

                        reverse = reverse_original

                        for id in range(reuseID, len(dic_topo[topo]['max_dir'])-1):
                            dirA,dirB = dic_topo[topo]['max_dir'][id:id+2]
                            if dirA == dirB:
                                dic_topo[topo]['allow_point'][id] = list(dic_topo[topo]['allow_point'][id])
                                dic_topo[topo]['allow_point'][id].sort(reverse = reverse)
                                dic_topo[topo]['allow_point'][id] = dic_topo[topo]['allow_point'][id]

                                dic_topo[topo]['allow_point'][id+1] = list(dic_topo[topo]['allow_point'][id+1])
                                dic_topo[topo]['allow_point'][id+1].sort(reverse = reverse)
                                dic_topo[topo]['allow_point'][id+1] = dic_topo[topo]['allow_point'][id+1]
                            else:
                                groupA = dic_topo[topo]['abut_group'][id]
                                groupB = dic_topo[topo]['abut_group'][id+1]
                                dic_topo[topo]['allow_point'][id+1] = list(dic_topo[topo]['allow_point'][id+1])
                                dic_topo[topo]['allow_point'][id] = list(dic_topo[topo]['allow_point'][id])
                                locA = [self.gen.dic_tile2loc[groupA][edge][0] for edge in self.gen.dic_tile2loc[groupA] if edge[0] == dirA][0]
                                locB = [self.gen.dic_tile2loc[groupB][edge][0] for edge in self.gen.dic_tile2loc[groupB] if edge[0] == dirB][0]
                                dic_topo[topo]['allow_point'][id].sort(reverse = reverse)
                                if dic_topo[topo]['max_dir'][id]:
                                    x1,y1 = (dic_topo[topo]['allow_point'][id][0],locA)
                                    x2,y2 = (locB,dic_topo[topo]['allow_point'][id+1][0])
                                else:   
                                    x2,y2 = (locA,dic_topo[topo]['allow_point'][id][0])
                                    x1,y1= (dic_topo[topo]['allow_point'][id+1][0],locB)
                                if (x2>x1 and y2<y1 ) or (y2>y1 and x2<x1):
                                    dic_topo[topo]['allow_point'][id+1].sort(reverse = reverse)
                                else:
                                    if reverse:reverse = False
                                    else: reverse = True
                                    dic_topo[topo]['allow_point'][id+1].sort(reverse = reverse)
                        reverse = reverse_original
                        for id in range(reuseID, 0,-1):
                            dirA,dirB = dic_topo[topo]['max_dir'][id], dic_topo[topo]['max_dir'][id-1]
                            if dirA == dirB:
                                dic_topo[topo]['allow_point'][id] = list(dic_topo[topo]['allow_point'][id])
                                dic_topo[topo]['allow_point'][id].sort(reverse = reverse)
                                dic_topo[topo]['allow_point'][id] = dic_topo[topo]['allow_point'][id]

                                dic_topo[topo]['allow_point'][id-1] = list(dic_topo[topo]['allow_point'][id-1])
                                dic_topo[topo]['allow_point'][id-1].sort(reverse = reverse)
                                dic_topo[topo]['allow_point'][id-1] = dic_topo[topo]['allow_point'][id-1]                        
                            else:
                                groupA = dic_topo[topo]['abut_group'][id]
                                groupB = dic_topo[topo]['abut_group'][id-1]
                                dic_topo[topo]['allow_point'][id-1] = list(dic_topo[topo]['allow_point'][id-1])
                                dic_topo[topo]['allow_point'][id] = list(dic_topo[topo]['allow_point'][id])
                                locA = [self.gen.dic_tile2loc[groupA][edge][0] for edge in self.gen.dic_tile2loc[groupA] if edge[0] == dirA][0]
                                locB = [self.gen.dic_tile2loc[groupB][edge][0] for edge in self.gen.dic_tile2loc[groupB] if edge[0] == dirB][0]
                                dic_topo[topo]['allow_point'][id].sort(reverse = reverse)
                                if dic_topo[topo]['max_dir'][id]:
                                    x1,y1 = (dic_topo[topo]['allow_point'][id][0],locA)
                                    x2,y2 = (locB,dic_topo[topo]['allow_point'][id-1][0])
                                else:   
                                    x2,y2 = (locA,dic_topo[topo]['allow_point'][id][0])
                                    x1,y1= (dic_topo[topo]['allow_point'][id-1][0],locB)
                                if (x2>x1 and y2<y1 ) or (y2>y1 and x2<x1):
                                    dic_topo[topo]['allow_point'][id-1].sort(reverse = reverse)
                                else:
                                    if reverse:reverse = False
                                    else: reverse = True
                                    dic_topo[topo]['allow_point'][id-1].sort(reverse = reverse)
                        for id in range(len(dic_topo[topo]['allow_point'])):
                            dic_topo[topo]['allow_point'][id] = tuple(dic_topo[topo]['allow_point'][id])
                        if mastergroup not in self.totaltopo:
                            self.totaltopo[mastergroup] = dic_topo
                        else:
                            self.totaltopo[mastergroup].update(dic_topo)
                            

                        for i in range(len(dic_topo[topo]['allow_point'])):
                            if len(dic_topo[topo]['allow_point'][i]):
                                abut_group = dic_topo[topo]['abut_group'][i]
                                max_dir = dic_topo[topo]['max_dir'][i]
                                start,end = dic_topo[topo]['allow_point'][i][0],dic_topo[topo]['allow_point'][i][-1]
                                start0_master = self.gen.dic_group2info[abut_group].group2set[max_dir][abut_group[0]][start]
                                end0_master = self.gen.dic_group2info[abut_group].group2set[max_dir][abut_group[0]][end]
                                start1_master = self.gen.dic_group2info[abut_group].group2set[max_dir][abut_group[1]][start]
                                end1_master = self.gen.dic_group2info[abut_group].group2set[max_dir][abut_group[1]][end]
                                print >>file,abut_group,start,end,start0_master,end0_master,start1_master,end1_master,max_dir
        file.close()
        self.totaltopo['mastergroup'] = grouporder
        self.totaltopo['group_unprocess'] = group_unprocess
        self.totaltopo['topo2reuseedge'] = self.dic_topo2reuseedge
        with mkdir('topo.pkl',mode='wb',type='data') as f:
            pickle.dump(self.totaltopo,f)
            


if __name__ == '__main__':
    commandLine, options, args = parseOptions(globals())
    config = getParams(options.config)
    reuse = Placecollapsepins()
    reuse.classify_ports()
    reuse.classify_groups()
    reuse.mergeport()
    reuse.getrelation()
    reuse.placeuniqports()

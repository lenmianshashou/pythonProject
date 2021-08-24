#!/tool/aticad/1.0/platform/RH6/bin/python

import getshape,copy,timeit,datetime
from fileparser import *
from collections import defaultdict
from getParams import *
from mkdir import mkdir
from create_csh_uniq import *
from optparse import *

def parseOptions(globals):
    """Parse all program options"""

    parser = OptionParser(description= "Place unique pins")

    parser.add_option("--config",
                      action="store", type="string", dest="config", help="Config file")

    parser.add_option("--outputDir",
                      action="store", type="string", dest="outputDir", help="Output directory")

    (options, args) = parser.parse_args()

    if not options.config:
        logger.error("--config must be specified")
        sys.exit(1)

    commandLine = ' ' . join(sys.argv)
    if args:
        logger.error("Extra arguments ('%s') found on end of command line" % ' ' . join(args))
        sys.exit(1)

    return commandLine, options, args
###global variation
dic_allowlayer = {}
class iterater_range(object):
    def __init__(self,start,end,step):
        self.start = start + step*32
        self.end = end - step*32
        self.step = step
        self.value = self.start
        self.setrange = set(xrange(start,end,step))
        
        self.tracknum = abs((self.end - self.start)/self.step)
    def __length_hint__(self):
        return  int((self.end -self.value)/self.step) if  self.end -self.value > self.step*3 else 0

    def __iter__(self):
        return self
    
    def __repr__(self):
        return 'Startfrom: %.3f Endto: %.3f Step: %.3f Now: %.3f' %(float(self.start)/2000, float(self.end)/2000, float(self.step)/2000,float(self.value)/2000)

    def next(self):
        if self.value < self.end:
            self.value += self.step
            return self.value
        else:
            return False

class pin_gen(object):
    def __init__(self,dic_tiles,chipname,dic_metal_dir):
        self.dic_orient = {'R0':'','MY':'','MX':'','R180':'',
                            'N':'','FS':'','S':'','FN':''}#These orient are legal 
        #self.dic_metal = {'M4':1,'M6':1,'M8':1,'M5':0,'M7':0,'M9':0}
        self.dic_metal_dir = dic_metal_dir
        self.create_generater(dic_tiles,chipname)
        self.dic_group2constraint = defaultdict(list)

    def get_pin_loc(self,group,num):
        single_use = 0
        port_generaters = sorted(self.dic_group2edge_iter[group].items(),key = lambda x: x[1].__length_hint__(),reverse = True)
        edges = []
        generaters = []
        for g in port_generaters:
            edges.append(g[0])
            generaters.append(g[1])

        #Ininital
        gen = 0
        loc_list = []
        edge = edges[gen]
        tile0_loc , tile1_loc= self.dic_tile2loc[group][edge]
        dic_relaxtion = {0:'Y',1:'X'}
        d = dic_relaxtion[edge[0]]
        while(num):
            if generaters[gen].__length_hint__():
                loc = generaters[gen].next()
                if edge[0]: # horizontal edges
                    for layer in dic_allowlayer[d]:
                        loc_list.append( ([loc, tile0_loc, layer], [loc, tile1_loc, layer]))
                else:
                    for layer in dic_allowlayer[d]:
                        loc_list.append( ([tile0_loc, loc, layer], [tile1_loc, loc, layer] ))
                num -= 1
            elif gen < len(edges) - 1:
                gen += 1
                edge = edges[gen]
                tile0_loc , tile1_loc= self.dic_tile2loc[group][edge]
            else:
                #use single pitch
                port_generaters = sorted(self.dic_group2edge_iter_single[group].items(),key = lambda x: x[1].__length_hint__(),reverse = True)
                edges = []
                generaters = []
                for g in port_generaters:
                    edges.append(g[0])
                    generaters.append(g[1])
                gen = 0
                edge = edges[gen]
                avail = sum(i.__length_hint__() for i in generaters)
                if single_use: 
                    print '#',group, num,avail
                    return  loc_list
                single_use = 1    
                tile0_loc , tile1_loc= self.dic_tile2loc[group][edge]
        return  loc_list
    
    def get_random_pin_loc(self,tile,num):
        groups = [g for g in self.dic_group2edge_iter if tile in g]
        loc_list = []
        if groups == []:
            return loc_list
        group_num = 0
        group = groups[group_num]
        port_generaters = sorted(self.dic_group2edge_iter[group].items(), key = lambda x: x[1].__length_hint__(),reverse = True)
        gen = 0
        edges = []
        generaters = []
        single_use = 0
        for g in port_generaters:
            edges.append(g[0])
            generaters.append(g[1])
        
        edge = edges[gen]
        avail = sum(i.__length_hint__() for i in generaters)
        #if num >= avail: print '#random:',group,num,avail
        tile_loc = self.dic_tile2loc[group][edge][group.index(tile)]
        pitch = self.dic_group2edge_iter
        dic_relaxtion = {0:'Y',1:'X'}
        d = dic_relaxtion[edge[0]]
        #add by kk
        tile0_loc , tile1_loc= self.dic_tile2loc[group][edge]

        while (num):
            if generaters[gen].__length_hint__():
                loc = generaters[gen].next()
                if edge[0]: # horizontal edges
                    for layer in dic_allowlayer[d]:
                        loc_list.append( ([loc, tile0_loc, layer], [loc, tile1_loc, layer]))
                else:
                    for layer in dic_allowlayer[d]:
                        loc_list.append( ([tile0_loc, loc, layer], [tile1_loc, loc, layer] ))
                num -= 1
            elif gen < len(edges) - 1:
                #find available ports within abutting edge
                gen += 1
                edge = edges[gen]
                tile_loc = self.dic_tile2loc[group][edge][group.index(tile)]
            elif group_num < len(groups) - 1:
                #find available ports in other abuting group
                group_num += 1
                group = groups[group_num]
                gen = 0
                edges = []
                generaters = []
                port_generaters = sorted(pitch[group].items(), key = lambda x: x[1].__length_hint__(),reverse = True)
                for g in port_generaters:
                    edges.append(g[0])
                    generaters.append(g[1])
                edge = edges[gen]
                #if num >= avail: print '#random:',group,num,avail
                tile_loc = self.dic_tile2loc[group][edge][group.index(tile)]
            else:
                #find available ports in single pitch 
                group_num = 0
                group = groups[group_num]
                gen = 0
                edges = []
                generaters = []
                pitch = self.dic_group2edge_iter_single
                port_generaters = sorted(pitch[group].items(), key = lambda x: x[1].__length_hint__(),reverse = True)
                for g in port_generaters:
                    edges.append(g[0])
                    generaters.append(g[1])
                edge = edges[gen]
                if single_use: 
                    if num >= avail: print '#random',group,num,avail
                    return  loc_list
                single_use = 1
                
                tile_loc = self.dic_tile2loc[group][edge][group.index(tile)]
        return loc_list

    def generate_pin_density(self,ratio = 1.1):
        with mkdir('placeuniquepins/pin_density.rpt') as f:
            for group in self.dic_group2edge_iter:
                for edge in self.dic_group2edge_iter[group]:
                    tileA,tileB = group
                    loc_A,loc_B = self.dic_tile2loc[group][edge]
                    generater = self.dic_group2edge_iter[group][edge]
                    if generater.start == generater.value: continue
                    if edge[0] == 0:
                        print >>f, 'Double_pitch', (loc_A,generater.start),(loc_A,generater.value)
                        print >>f, 'Double_pitch', (loc_B,generater.start),(loc_B,generater.value)
                    else:
                        print >>f, 'Double_pitch', (generater.start,loc_A),(generater.value,loc_A)
                        print >>f, 'Double_pitch', (generater.start,loc_B),(generater.value,loc_B)

            for group in self.dic_group2edge_iter_single:
                
                for edge in self.dic_group2edge_iter_single[group]:
                    tileA,tileB = group
                    loc_A,loc_B = self.dic_tile2loc[group][edge]
                    generater = self.dic_group2edge_iter_single[group][edge]
                    if generater.start == generater.value: continue
                    if edge[0] == 0:
                        print >>f, 'Single_pitch', (loc_A,generater.start),(loc_A,generater.value)
                        print >>f, 'Single_pitch', (loc_B,generater.start),(loc_B,generater.value)
                    else:
                        print >>f, 'Single_pitch', (generater.start,loc_A),(generater.value,loc_A)
                        print >>f, 'Single_pitch', (generater.start,loc_B),(generater.value,loc_B)
        pkl_name = '%s/data/port_analysis.pkl' % options.outputDir
        if os.path.exists(pkl_name):
            with mkdir(file_name = 'port_analysis.pkl', mode = 'rb',type = 'data') as file:
                def_file = []
                db = pickle.load(file)
                self.dic_abuttile2nets = db['dic_abuttile2nets']
                self.dic_othertile2nets = db['dic_othertile2nets']
            self.dic_group2track = defaultdict(int)
            self.dic_tile2group = defaultdict(dict)
            self.dic_tile2margin = defaultdict(int)
            for group in self.dic_group2edge_iter:
                for edge in self.dic_group2edge_iter[group]:
                    self.dic_group2track[group] += self.dic_group2edge_iter[group][edge].tracknum*3
                    self.dic_group2track[(group[-1],group[0])] += self.dic_group2track[group]
                if group in self.dic_abuttile2nets:
                    self.dic_tile2group[group[0]][group] = sum(self.dic_abuttile2nets[group][g] for g in self.dic_abuttile2nets[group])
                if (group[-1],group[0]) in self.dic_abuttile2nets:
                    self.dic_tile2group[group[-1]][(group[-1],group[0])] = sum(self.dic_abuttile2nets[(group[-1],group[0])][g] for g in self.dic_abuttile2nets[(group[-1],group[0])])

            for tile in self.dic_tile2group:
                for group in self.dic_tile2group[tile]:
                    tmp = self.dic_group2track[group] - self.dic_tile2group[tile][group]*ratio
                    if tmp > 0: tmp = 0
                    self.dic_tile2margin[tile] += tmp

            tuple_tile2margin = sorted(self.dic_tile2margin.items(),key = lambda x:x[1])
            
            with mkdir('placeuniquepins/pin_density_mft.rpt') as f: 
                print >>f,'%-40s %-10s %-10s %-10s %-10s %-10s' %('group', 'func ports','feed ports', 'violation','length_slack','length_single_slack')
                dic_topo = {}
                for tile in tuple_tile2margin:
                    tile = tile[0]
                    print >>f,'##Tile: ',tile
                    for group in  self.dic_tile2group[tile]:
                        feed = 0
                        func = 0
                        track = self.dic_group2track[group]
                        TOPO = []
                        for topo in self.dic_abuttile2nets[group]:
                            TOPO.append(' '.join(topo))
                            if topo.index(tile) == 0:
                                func += self.dic_abuttile2nets[group][topo]
                                dic_topo[topo] = 'abut'
                            else:
                                feed += self.dic_abuttile2nets[group][topo]
                                dic_topo[topo] = 'feed'
                        slack = track - int(feed*ratio) - func
                        print >>f,'*%-40s %-10s %-10s %-10s %-10s %-10s' %(' '.join(group),func, feed,slack,(float(slack)/3+1)*312/2000,(float(slack)/4+1)*312/2000)
                        for topo in self.dic_abuttile2nets[group]:
                            print >>f,'         group: %-40s num: %d topo:%s' %(' '.join([topo[0],topo[-1]]),self.dic_abuttile2nets[group][topo],dic_topo[topo])
            print 'Pin density report generated'

    def create_generater(self,dic_tiles,chipname):
        self.dic_group2edge_iter = defaultdict(dict)
        self.dic_group2edge_iter_single = defaultdict(dict)
        

        self.dic_tile2loc = defaultdict(dict)
        self.dic_tile2track = {}
        self.dic_track2pitch = {}

        dic_rotate_metal = {'M6':'M7','M7':'M6','M8':'M9','M9':'M8','M10':'M11','M11':'M10'}
        for tile in dic_tiles:
            dic_metal = defaultdict(list) #Note the variable is different with self.dic_metal
            for metal in dic_tiles[tile].tile_master.track:
                for track in dic_tiles[tile].tile_master.track[metal]:
                    if metal in self.dic_metal_dir: 
                        self.dic_track2pitch[metal] = track[-1]
                        if self.dic_metal_dir[metal] == 0: #0 - vertical abutment
                            locs = ((0,track[1]),(0,track[1] + track[2] * track[3]))
                        else:
                            locs = ((track[1],0),(track[1] + track[2] * track[3],0))
                    else:
                        continue
                    #Get origin  coordinates *2000 to fix python float bug
                    if dic_tiles[tile].inst_orient in getshape.dic_legal:
                        x_min, y_min, x_max, y_max = dic_tiles[tile].tile_master.origin
                    else:
                        y_min, x_min, y_max, x_max = dic_tiles[tile].tile_master.origin
                    #x_min, y_min, x_max, y_max = dic_tiles[tile].tile_master.origin
                    track_loc = []
                    for loc in locs:
                        loc_new = getshape.dic_orientation[dic_tiles[tile].inst_orient](loc)
                        loc_chip = list(dic_tiles[tile].inst_loc)
                        loc_chip[0] += abs(x_min)
                        loc_chip[1] += abs(y_min)
                        loc = [loc_chip[0] + loc_new[0], loc_chip[1] + loc_new[1]]
                        track_loc.append(loc)
                    if dic_tiles[tile].inst_orient not in  self.dic_orient:
                        metal = dic_rotate_metal.get(metal,metal)
                    if track_loc[0][0] == track_loc[1][0]:
                        for t in track_loc:
                            dic_metal[metal].append(t[1])# Track start point
                    else:
                        for t in track_loc:
                            dic_metal[metal].append(t[0])# Track start point
        

            for metal in dic_metal:
                dic_metal[metal].sort()
            self.dic_tile2track[tile] = dic_metal
                #self.dic_tile2track[tile][metal].sort(reversed = True)
            for abut in dic_tiles[tile].abut_inst:
                group  = tuple(sorted([tile,abut[2]]))
                edge = abut[-1] 
                x_y = edge[0]
                if tile == abut[2]: continue
                pitch = 400
                if abut[0][x_y] - abut[1][x_y] < 0 and chipname not in (tile, abut[2]):
                    self.dic_tile2loc[(tile, abut[2])][edge] = (abut[0][x_y] - pitch, abut[1][x_y] + pitch)
                    self.dic_tile2loc[(abut[2], tile)][edge] = (abut[1][x_y] + pitch, abut[0][x_y] - pitch)
                elif abut[0][x_y] - abut[1][x_y] >= 0 and chipname not in (tile, abut[2]):
                    self.dic_tile2loc[(tile, abut[2])][edge] = (abut[0][x_y] + pitch, abut[1][x_y] - pitch)
                    self.dic_tile2loc[(abut[2], tile)][edge] = (abut[1][x_y] - pitch, abut[0][x_y] + pitch)
                elif chipname in (tile, abut[2]):
                    index = (tile, abut[2]).index(chipname)
                    if abut[index][x_y] - abut[(index+1)%2][x_y] < 0:
                        self.dic_tile2loc[(tile, abut[2])][edge] = (abut[0][x_y] + pitch, abut[1][x_y] + pitch)
                        self.dic_tile2loc[(abut[2], tile)][edge] = (abut[1][x_y] + pitch, abut[0][x_y] + pitch)
                    else:
                        self.dic_tile2loc[(tile, abut[2])][edge] = (abut[0][x_y] - pitch, abut[1][x_y] - pitch)
                        self.dic_tile2loc[(abut[2], tile)][edge] = (abut[1][x_y] - pitch, abut[0][x_y] - pitch)
                #Suppose M4,M6,M8 with some pitch
                #if x_y: 
                #    loc_tmp = copy.deepcopy(self.dic_tile2track[tile]['M5'])
                #    pitch = self.dic_track2pitch['M5']
                #else:
                #    loc_tmp = copy.deepcopy(self.dic_tile2track[tile]['M4'])
                #    pitch = self.dic_track2pitch['M4']
                loc_tmp = copy.deepcopy(self.dic_tile2track[tile][self.dic_metal_dir[x_y]])
                pitch = self.dic_track2pitch[self.dic_metal_dir[x_y]]
                left,right = edge[1], edge[2]
                loc_tmp.append(left)
                loc_tmp.sort()
                loc_index = loc_tmp.index(left)
                if loc_index%2 == 1:  #if  loc_index%2 == 1 , means: pitch startpoint ->common edge start point
                    start_point = (int((loc_tmp[loc_index] - loc_tmp[loc_index - 1])/pitch) + 1)*pitch + loc_tmp[loc_index - 1]
                else:
                    start_point = loc_tmp[loc_index + 1]
                loc_tmp.remove(left)

                loc_tmp.append(right)
                loc_tmp.sort()
                loc_index = loc_tmp.index(right)
                if loc_index%2 == 1 : #if  loc_index%2 == 1 , means:common edge end point -> pitch endpoint 
                    end_point = (int((loc_tmp[loc_index] - loc_tmp[loc_index - 1])/pitch) + 1)*pitch + loc_tmp[loc_index - 1]
                else:
                    end_point = loc_tmp[loc_index - 1]
                loc_tmp.remove(right)
                self.dic_group2edge_iter[group][edge] = iterater_range(start_point,end_point,pitch*2)
                self.dic_group2edge_iter_single[group][edge] = iterater_range(start_point+pitch,end_point,pitch*2)
        with mkdir('placeuniquepins/edge_avail.rpt') as f:
            for group in self.dic_group2edge_iter:
                print >>f, group[0], self.dic_tile2track[group[0]]
                print >>f, group[1], self.dic_tile2track[group[1]]
                for edge in self.dic_group2edge_iter[group]:
                    edge_new = [float(i)/2000 for i in edge]
                    print >>f, group, edge_new, [float(i)/2000 for i  in self.dic_tile2loc[group][edge]]
                    print >>f, group, edge_new, self.dic_group2edge_iter[group][edge]
                    print >>f, group, edge_new, self.dic_group2edge_iter_single[group][edge]

        #self.generate_pin_density()

class UniqPinAssign(object):
    def __init__(self):
        
        self.params = getParams(params = options.config)
        #self.params = getParams(params = '/proj/fcfp11/work_area/tzhang1/ICC2_tahiti_compute_array/pdscripts/pinassign_tahiti_ca.cfg')
        self.info = self.params.jsonconf['unique']
        self.layer_info()
        self.shape = getshape.getshape()
        self.conn = parser_netconn(file= self.info["NETCONN"],read_from_pkl = False,filter_fan = False)
        self.chipname = chipname = str(self.info["CHIPNAME"])
        self.shape.parsedef(file=self.info["DEF"],read_from_pkl = self.info["DEF_READ_FROM_PKL"],pkl_name = 'getshape_unique.pkl',chipname = self.chipname,track_valid = eval(self.info['VALIDTRACK']) )
        self.shape.getReuse()
        self.shape.getabuttile()
        self.shape.sortabutlistbycommonedge()
        self.shape.filter_edge(space = int(self.info['SPACE_FOR_ABUT_LIMIT']))
        self.readbkg = getshape.get_blockage(self.shape,tune = self.info["BKG"])
        self.ports_classify()
        self.dirname = options.outputDir

    def layer_info(self):
        '''
            Get layer information
        '''
        VALIDTRACK = eval(self.info['VALIDTRACK'])
        LAYERINDEX = eval(self.info['LAYERINDEX'])
        self.dic_metal = {}  #layer -> index
        self.dic_metal_dir = {} #Layer -> 'track X|Y', reverse of validtrack dictionary
        self.dic_width = eval(self.info['PINWIDTH'])
        global dic_allowlayer
        dic_allowlayer = eval(self.info['ALLOWLAYER'])
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

    def ports_classify(self):
        '''
            classify ports into abut and non-abut 
        '''
        self.dic_abuttile2nets = defaultdict(list)
        self.dic_othertile2nets = defaultdict(list)
        for net in  self.conn.dic_net2driv:
            port = self.conn.dic_net2driv[net][0]
            if '/' not in port:
                self.conn.dic_net2driv[net][0] = '/'.join([self.chipname,port])
            if self.conn.dic_net2load[net] != []:
                port = self.conn.dic_net2load.get(net,['/'])[0]
                if '/' not in port:
                    self.conn.dic_net2load[net][0] = '/'.join([self.chipname,port])
                    
        for net in  self.conn.dic_net2driv:
            if len(self.conn.dic_net2driv[net]) != 1 or len(self.conn.dic_net2load[net]) != 1:
                for port in self.conn.dic_net2driv[net] :
                    if '/' not in port: 
                        tile = self.chipname
                        port = '/'.join([self.chipname,port])
                    else:
                        tile  = port.split('/',1)[0]
                    if tile in self.shape.dic_inst2master:
                        self.dic_othertile2nets[tile].append(port)
                for port in self.conn.dic_net2load[net] :
                    tile  = port.split('/',1)[0]
                    if tile in self.shape.dic_inst2master:
                        self.dic_othertile2nets[tile].append(port)
            else:
                tileA = self.conn.dic_net2driv[net][0].split('/',1)[0]
                tileB = self.conn.dic_net2load[net][0].split('/',1)[0]
                
                if tileA not in self.shape.dic_inst2master and tileB in self.shape.dic_inst2master:
                    self.dic_othertile2nets[tileB].append(self.conn.dic_net2load[net][0])
                elif tileA in self.shape.dic_inst2master and tileB not in self.shape.dic_inst2master:
                    self.dic_othertile2nets[tileA].append(self.conn.dic_net2driv[net][0])
                elif tileA in self.shape.dic_inst2master and tileB in self.shape.dic_inst2master:
                    if tileA == tileB:
                        self.dic_othertile2nets[tileA].append(self.conn.dic_net2driv[net][0])
                        self.dic_othertile2nets[tileB].append(self.conn.dic_net2load[net][0])
                    else:
                        self.dic_abuttile2nets[(tileA,tileB)].append((self.conn.dic_net2driv[net][0],self.conn.dic_net2load[net][0]))
        self.numofother = 0
        for tile in self.dic_othertile2nets:
            self.numofother +=  len(self.dic_othertile2nets[tile])
        self.numofabut = 0
        for tile in self.dic_abuttile2nets:
            self.numofabut +=  len(self.dic_abuttile2nets[tile])*2

    def placeuniqpins(self):
        '''
        '''
        RPT = mkdir_open('placeuniquepins/dic_ports2loc.rpt')
        pin_generater = pin_gen(self.shape.dic_tiles,self.chipname,self.dic_metal_dir)
        self.dic_ports2loc = defaultdict(dict)
        self.dic_unplace_ports = {}
        for group in self.dic_abuttile2nets:
            numofnets = len(self.dic_abuttile2nets[group])/3 + 1 #pair
            group_new = list(group)
            group_new.sort()
            group_new = tuple(group_new)
            #print group,numofnets
            if group_new not in pin_generater.dic_group2edge_iter:
                print >>RPT, 'group_new:',group_new
                continue
            port_locs = pin_generater.get_pin_loc(group_new,numofnets)
            index = 0
            length = len(port_locs)
            print >>RPT,'## Group name:', group, 'numofnets:',numofnets
            for (port0, port1) in sorted(self.dic_abuttile2nets[group]):
                tile0, pin0 = port0.split('/',1)
                tile1, pin1 = port1.split('/',1)
                index_0 = group_new.index(tile0)
                index_1 = group_new.index(tile1)
                if index == length:
                    print >>RPT,"#Error: remaining ports have no location"
                    break
                #self.dic_ports2loc[tile0].append( (pin0, port_locs[index][index_0]) )
                #self.dic_ports2loc[tile1].append( (pin1, port_locs[index][index_1]) )
                self.dic_ports2loc[tile0][pin0] = tuple(port_locs[index][index_0])
                self.dic_ports2loc[tile1][pin1] = tuple(port_locs[index][index_1])
                print >>RPT, tile0, pin0, tile1, pin1
                print >>RPT, port_locs[index][index_0], port_locs[index][index_1]
                index += 1
                
        for t in self.dic_othertile2nets:
            index = 0
            numofnets = len(self.dic_othertile2nets[t])/3 + 1
            #print t,numofnets
            print >>RPT,'## Group name:',t, 'numofothernets:', numofnets
            port_locs = pin_generater.get_random_pin_loc(t,numofnets)
            length = len(port_locs)
            for port in self.dic_othertile2nets[t]:
                if index == length: 
                    print >>RPT,"#Error: remaining ports have no location"
                    break
                tile0, pin0 = port.split('/',1)
                #self.dic_ports2loc[tile0].append( (pin0, port_locs[index][index_0]) )
                #change by kk
                #self.dic_ports2loc[tile0][pin0] = tuple(port_locs[index])
                self.dic_ports2loc[tile0][pin0] = tuple(port_locs[index][index_0])
                print >>RPT, tile0, pin0
                print >>RPT, port_locs[index]
                index += 1
               
        RPT.close()
        pin_generater.generate_pin_density()
    def placemasterpins(self):
        '''
            Transfer instance ports location to its master;
        '''
        print 'start:placemasterpins'
        #self.dic_ports2loc_master = copy.deepcopy(self.dic_ports2loc)
        with mkdir('placeuniquepins/port_transfer.rpt') as f:
            for tile in self.dic_ports2loc:
                inst_loc = self.shape.dic_tiles[tile].inst_loc
                if  self.shape.dic_tiles[tile].inst_orient in getshape.dic_legal:
                    ref_x_min, ref_y_min = [abs(i) for i in self.shape.dic_tiles[tile].tile_master.origin[0:2]]
                else:
                    ref_y_min, ref_x_min = [abs(i) for i in self.shape.dic_tiles[tile].tile_master.origin[0:2]]
                for port in self.dic_ports2loc[tile]:
                    location = self.dic_ports2loc[tile][port]
                    #print tile,port
                    #print self.dic_ports2loc[tile][port]
                    print >>f,'Inst:',tile,port,location,(float(location[0])/2000,float(location[1])/2000)
                    x, y, metal = location                    
                    #print >>f,'loc:',loc
                    new_loc = [x - inst_loc[0] - ref_x_min, y - inst_loc[1] - ref_y_min]
                    #print >>f,'new_loc',new_loc, inst_loc,ref_x_min, ref_y_min
                    new_loc = getshape.dic_orientation_reversed[ self.shape.dic_tiles[tile].inst_orient](new_loc[0:2])
                    #print >>f,'new_loc',new_loc
                    new_loc_divide2000 = (float(new_loc[0])/2000,float(new_loc[1])/2000)
                    self.dic_ports2loc[tile][port] = new_loc_divide2000 + (metal,)
                    print >>f,'Mast:',self.shape.dic_tiles[tile].tile_master.ref_name,port,new_loc,new_loc_divide2000

        print 'End:placemasterpins'

    def write_tcl(self):
        dic_masterwithport = {}
        for tile in self.shape.dic_master2inst:
            filedir = 'data/PartitionUnique/%s' %tile
            if os.path.exists(filedir):
                pass
            else:
                os.makedirs(filedir)
        for tile in self.dic_ports2loc:
            master_tile = self.shape.dic_inst2master[tile]
            dic_masterwithport[master_tile] = ''
            filedir = '%s/data/placeuniquepins/%s/%s' % (self.dirname,master_tile,master_tile)
            if os.path.exists(filedir):
                pass
            else:
                os.makedirs(filedir)
            with mkdir('placeuniquepins/%s.tcl' % master_tile , type = 'data') as f:
                index = 0
                for (port, loc) in  self.dic_ports2loc[tile].items():
                    print >>f, "set_individual_pin_constraints -ports %s -location { %.4f %.4f } -allowed_layers %s" %( port, loc[0], loc[1], loc[2]) 
        rest = set(self.shape.dic_master2inst) - set(dic_masterwithport)
        print 'Total %s tiles, %s tiles with ports' %(len(self.shape.dic_master2inst),len(dic_masterwithport))
        for tile in rest:
            with mkdir('placeuniquepins/%s.tcl' % tile, type = 'data') as f:
                    print >>f, "#TOUCH"
            filedir = '%s/data/placeuniquepins/%s/%s' % (self.dirname,tile,tile)
            if os.path.exists(filedir):
                pass
            else:
                os.makedirs(filedir)
    def write_csh(self):
        
        tmp = create_csh(self.shape)
        tmp.create_ndm(inputdef = 'data/PartitionUnique',
                            inputverilog = 'data/PartitionUnique',
                            source_file = []
            )
        tmp.pre_create_pindef(inputdef = 'data/PartitionUnique',
                            inputverilog = 'data/PartitionUnique',
                            source_file = []
            )
        tmp.create_pinplace_def(inputdef = 'data/PartitionUnique',
                            inputverilog = 'data/PartitionUnique',
                            source_file = []
            )
        os._exit(0)
        print 'done'
    def report_ports(self,save_picture = True): 
        '''
            1. report ports categories (4 types:
                1. abut ports
                2. float ports
                3. IO buffer related ports
                4. multi-driven ports
                )
            2. check tiles within abutting port group whether abutted or not

        '''
        with mkdir('UniqPinAssign/report_ports.rpt') as f:
            print >>f, 'Ports number(abut) %d' % self.numofabut
            print >>f, 'Ports number(others) %d' %  self.numofother
            dic_group = {}
            for group in self.conn.dic_tile2net:
                driv, load = [i.split('/',1)[0] for i in group]
                if driv == load: continue
                #filter driv/load group which is not tile group
                if driv not in self.shape.dic_inst2master or load not in self.shape.dic_inst2master:
                    continue
                #Get driv's master name
                driv_master = self.shape.dic_inst2master[driv]
                abut_edges = [abut for abut in self.shape.dic_tiles[driv].abut_inst if abut[2] == load] #check wheter driv has common edge(s) with driv
                if len(abut_edges) == 0 :#if group has no common edge
                    dic_group[group] = len(self.conn.dic_tile2net[group])
            print >>f, 'Error: Following groups are not abutting by script checking:'
            print >>f, '%20s %20s %5s' % ('driv', 'load', 'num')
            for group in dic_group:
                if len(set(group)) == 1: continue
                print >>f, '%20s %20s %5s' % (group[0], group[1], dic_group[group])

if __name__ == '__main__':
    commandLine, options, args = parseOptions(globals())
    tmp = UniqPinAssign()
    tmp.report_ports() 
    tmp.placeuniqpins()
    tmp.placemasterpins()
    tmp.write_tcl()

    #csh = create_csh(tmp.shape)
    #tmp.create_I2tcl()  
    #tmp.create_ndm(inputdef = 'data/InsertFeedThruUnique',
    #                        inputverilog = 'data/InsertFeedThruUnique',
    #                        source_file = ['ppjiang/tcls/getshape/%s_bkg.tcl']
    #        )
    #tmp.pre_create_pindef(inputdef = 'data/InsertFeedThruUnique',
    #                        inputverilog = 'data/InsertFeedThruUnique',
    #                        source_file = []
    #        )
    #tmp.create_pinplace_def(inputdef = 'data/InsertFeedThruUnique',
    #                        inputverilog = 'data/InsertFeedThruUnique',
    #                        source_file = ['ppjiang/tcls/getshape//%s_bkg.tcl']
    #        )
    ##tmp.write_csh()
    #tmp.create_I2tcl()

'''
     Contact: Pengpeng Jiang, 03A312 (Shanghai - Derek Cheng), EXT
     Date: 02/28/2018
     Maintainer: ppjiang xguchen 
     Version:1.20
'''
from metrics import gzopen
import re,glob
import math
import logging
from collections import defaultdict
import numpy as np
import threading
import colors
import weakref
import cPickle as pickle
import os,subprocess
from mkdir import *
from shapely.geometry import Polygon
from shapely.geometry import Point
#Display more info for debug
debug_mode = True

dic_legal = {
    'N':lambda loc: (loc[0],loc[1]),
    'FN':lambda loc: (-loc[0],loc[1]),
    'S':lambda loc: (-loc[0],-loc[1]),
    'FS':lambda loc: (loc[0],-loc[1]),
}
dic_orientation = {
    'E':lambda loc: (loc[1],-loc[0]),
    'N':lambda loc: (loc[0],loc[1]),
    'FN':lambda loc: (-loc[0],loc[1]),
    'S':lambda loc: (-loc[0],-loc[1]),
    'FS':lambda loc: (loc[0],-loc[1]),
    'FE':lambda loc: (loc[1],loc[0]),
    'W':lambda loc: (-loc[1],loc[0]),
    'FW':lambda loc: (-loc[1],-loc[0]),
}

dic_orientation_reversed = {
    'E':lambda loc: (-loc[1],loc[0]),
    'N':lambda loc: (loc[0],loc[1]),
    'FN':lambda loc: (-loc[0],loc[1]),
    'S':lambda loc: (-loc[0],-loc[1]),
    'FS':lambda loc: (loc[0],-loc[1]),
    'FE':lambda loc: (loc[1],loc[0]),
    'W':lambda loc: (loc[1],-loc[0]),
    'FW':lambda loc: (-loc[1],-loc[0]),
}




    

class Tile_Master(object):
    def __init__(self,ref_name,color,ref_poly):
        self.ref_name = ref_name
        self.color = color
        self.ref_poly = ref_poly
        self.edges = {} #Store edges 
        self.allowedge = {} #Store edges allowing feedthrough
        self.origin = ()  #Store leftbottom and topright origin
        self.pitch = {'M6':{'X':[('start','do','pitch')],'Y':[('start','do','pitch')]}}
        self.edgeside = {} #clock_wise 1,2,...,N
        self.point = {}
#type(New_class,(),{})
#we want to define tile master meta class like
#class df_cs_umc_t(object):
#    ref_name = 'df_cs_umc_t'
#    color = 'red'
#    ref_poly = []
#    edges = {}
#    allowedge = {}
#    origin = ()

class Tile_Instance(object):
    def __init__(self,tile_master_class):
        self.inst_name = ''

        self.abut_inst = []
        self.edges = {}
        self.allowedge = {}

        self.reuse_list = []
        self.inst_ploy = []
        self.inst_loc = []
        self.inst_size = []  #(width, height)
        self.inst_orient = ''
        self.tile_master = tile_master_class

    def __str__(self):
        return '(Tile:%s %s,)' %(self.ref_name , self.inst_name)


class chip(object):
    def __init__(self):
        self.dic_tiles = {}

class getshape(chip):
    def __init__(self):
        #Tile -> polygen shape
        super(getshape,self).__init__()
        self.dic_tile2poly = defaultdict(list)
        #Tile -> rect shape
        self.dic_tile2rect = {}
        self.dic_params = {}
        self.dic_inst2masterinfo = {}
        #log file for getshape:
        tmp_name = os.popen("who | cut -d' ' -f1 | sort | uniq").readlines()[0].strip()
        self.LOG = open('getshape.log'+tmp_name,'w+')
        #print getshape.instances
        #ref_edge to inst_edge
        self.dic_ref2inst = {}
        self.dic_inst2ref = {}
        #
        self.dic_tile2track = {}
        self.dic_tile2offset = {}
        self.dic_edge2pindir = defaultdict(dict)
        #self.dic_instintedge2floatedge = defaultdict(dict) #Instance int point to float point 
    def __params__(self,doc):
        regx = re.compile(r'(\S+)\s*=\s*(.*)')
        for line in doc.split('\n'):
            line = line.strip()
            m = regx.search(line)
            if m:
                tmp = m.groups()
                #print "Add new params",tmp
                self.dic_params[tmp[0]] = tmp[1]
    


    def sortabutlistbycommonedge(self):
        def cmp(x,y):
            x = x[-1]
            y = y[-1]
            x_set = set(range(0,x[2] - x[1],2000))
            y_set = set(range(0,y[2] - y[1],2000))
            if len(x_set) > len(y_set):
                return -1
            else:
                return 1
        for tile in self.dic_tiles:
            self.dic_tiles[tile].abut_inst = sorted(self.dic_tiles[tile].abut_inst,cmp)  
        #print self.dic_tiles['df_cake_t1'].abut_inst
        #for tile in self.dic_tiles:
        #    self.dic_tiles[tile].abut_inst = sorted(self.dic_tiles[tile].abut_inst,key = lambda x:x[3])
    
    def checkabut(self,threshold = 2):
        self.checkabut = {}
        for tile in self.dic_tiles:
            if self.chipname  != tile:
                a = 0
                b = 1
            else:
                a = 1
                b = 0
            for abut_info in self.dic_tiles[tile].abut_inst:
                v_h = abut_info[3][0] ##vertical = 0 horizontal = 1
                if v_h:
                    point = Point((abut_info[0][0] + abut_info[0][2])/2,abut_info[0][1] - threshold)
                    polygon = Polygon(self.dic_tiles[tile].inst_poly)
                    if point.within(polygon):
                        self.checkabut[abut_info] = a
                    else:
                        self.checkabut[abut_info] = b
                else:
                    point = Point(abut_info[0][0] - threshold, (abut_info[0][1] + abut_info[0][3])/2)
                    polygon = Polygon(self.dic_tiles[tile].inst_poly)
                    if point.within(polygon):
                        self.checkabut[abut_info] = a
                    else:
                        self.checkabut[abut_info] = b
                #if abut_info[2] == 'df_rpt_16_t':
                #print abut_info,self.checkabut[abut_info]
    def inst2master(self,inst,points):
        '''
            Transfer coordinate from chip to tile
            points are iterable [(x,y),...(m,n)] varibles.
        '''
        inst2master = []
        inst_orient = self.dic_tiles[inst].inst_orient
        if inst_orient in dic_legal:
            ref_x_min, ref_y_min = [abs(i) for i in self.dic_tiles[inst].tile_master.origin[0:2]]
        else:
            ref_y_min, ref_x_min = [abs(i) for i in self.dic_tiles[inst].tile_master.origin[0:2]]
        inst_loc = self.dic_tiles[inst].inst_loc
        for (i,m) in points:
            inst2master.append(dic_orientation_reversed[inst_orient]((i-inst_loc[0]-ref_x_min, m-inst_loc[1]-ref_y_min)))
        return inst2master

    def master2inst(self,master,points):
        '''
            Transfer coordinate from tile to chip.
            points are iterable [(x,y),...(m,n)] varibles.
        '''
        dic_master2inst = defaultdict(list)
        for inst in self.dic_master2inst[master]:
            x_min, y_min, x_max, y_max = self.dic_tiles[inst].tile_master.origin
            points_array = np.array(points)
            tmp1 = np.array([[abs(x_min) + self.dic_tiles[inst].inst_loc[0], abs(y_min) + self.dic_tiles[inst].inst_loc[1]] for i in range(points_array.shape[0])])
            tmp2 = np.array([dic_orientation[self.dic_tiles[inst].inst_orient](point) for point in points_array])
            tmp3 = tmp1 + tmp2
            dic_master2inst[inst] = tmp3
        return dic_master2inst


    def filter_edge(self,exclude_tiles=['compute_array0'],space = 8000000,overlap_limit = 30):
        '''
            filter abut_inst by some limit, such as space, overlap area
        '''
        dic_user_definedabut = {}
        dic_master2bkg = defaultdict(dict)
        with mkdir('getshape/filter_edge.tune',type = 'tunes',mode = 'r+') as f:
            mt = re.compile(r'(\S+)\s+(\S+)')
            for line in f:
                line = line.strip().split('#',1)[0]
                pt = mt.search(line)
                if pt:
                    a = pt.groups()
                    dic_user_definedabut[a] = ''
                    dic_user_definedabut[(a[1],a[0])] = ''
        with mkdir('getshape/filter_edge.rpt') as f:
            for tile in self.dic_inst2master:
                dic_abutedge = {}
                abut_inst = []
                for abut in self.dic_tiles[tile].abut_inst:
                    if tile == abut[2]: continue
                    group = (tile,abut[2])
                    if group in dic_user_definedabut:
                        if len(set(range(0,abs(abut[-1][1] - abut[-1][2]),2000))) <= 5:
                            continue
                        if abut[0][0] == abut[0][2]:#edge is vertical
                            Space = abut[0][0] - abut[1][0]
                        else: #edge is horizontal
                            Space = abut[0][1] - abut[1][1]
                        if abs(Space) > 1000*2000: 
                            continue
                        abut_inst.append(abut)
                        dic_abutedge[abut[0]] = ''
                    else:
                        if len(set(range(0,abs(abut[-1][1] - abut[-1][2]),2000))) <= overlap_limit:
                            continue
                        if abut[0][0] == abut[0][2]:#edge is vertical
                            
                            Space = abut[0][0] - abut[1][0]
                        else: #edge is horizontal
                            Space = abut[0][1] - abut[1][1]
                        if abs(Space) > int(space): 
                            continue
                        dic_abutedge[abut[0]] = ''
                        abut_inst.append(abut)
                #Update abut_inst value after filter
                print >>f,tile
                print >>f,'Orignal abut list:',self.dic_tiles[tile].abut_inst
                print >>f,'Filtered abut list:',abut_inst
                self.dic_tiles[tile].abut_inst = abut_inst

            ###Following code is for creating pin assign blockage
                for edge in self.dic_tiles[tile].tile_master.edges:
                    inst_edge = self.dic_ref2inst[tile][edge]
                    mst = self.dic_inst2master[tile]
                    if inst_edge not in dic_abutedge:
                        if edge[0] == edge[2]:
                            blk = 'create_pin_blockage -boundary {{%.3f %.3f} {%.3f %.3f}}  -layers {M0 M2 M4 M6 M8 M10}' %(float(edge[0] + 600)/2000,float(edge[1])/2000,float(edge[2]-600)/2000,float(edge[3])/2000)
                            
                        else:
                            blk = 'create_pin_blockage -boundary {{%.3f %.3f} {%.3f %.3f}}  -layers {M1 M3 M5 M7 M9 M11}' %(float(edge[0])/2000,float(edge[1] + 600)/2000,float(edge[2])/2000,float(edge[3]-600)/2000)
                        if mst in dic_master2bkg  and blk in dic_master2bkg[mst]:
                            dic_master2bkg[mst][blk] += 1
                        else:
                            dic_master2bkg[mst][blk] = 1
                        
            for master in dic_master2bkg:
                filename = 'getshape/%s_bkg.tcl' % master
                with mkdir(filename,type='tcls') as g:
                    for line in dic_master2bkg[master]:
                        if dic_master2bkg[master][line] == len(self.dic_master2inst[master]):
                            print >>g, line
    def getReuse(self):
        '''
        self.dic_inst2master = defaultdict(list)
        #Tile:[Tile_reuse0,...,Tile_reuseN]
        self.dic_master2inst = {}
        #Tile_reuse0:Tile,....Tile_reuseN:Tile
        '''
        self.dic_inst2master = {}
        self.dic_master2inst = defaultdict(list)

        for tile in self.dic_tiles:
            self.dic_inst2master[self.dic_tiles[tile].inst_name] = self.dic_tiles[tile].tile_master.ref_name
            self.dic_master2inst[self.dic_tiles[tile].tile_master.ref_name].append( self.dic_tiles[tile].inst_name)

    def update_edge(self,instance):
        '''
            update allows edge for reuse tiles of instance
        '''
        if instance not in self.dic_tiles: return 0
        reuse_list =  self.dic_master2inst[self.dic_inst2master[instance]]
        for edge in self.dic_tiles[instance].allowedge:
             
            allow_edge = self.dic_tiles[instance].allowedge[edge]
            if edge == allow_edge: continue
            inst_loc = self.dic_tiles[instance].inst_loc
            if self.dic_tiles[instance].inst_orient in self.dic_legal:
                ref_x_min, ref_y_min = [abs(i) for i in self.dic_tiles[instance].tile_master.origin[0:2]]
            else:
                ref_y_min, ref_x_min = [abs(i) for i in self.dic_tiles[instance].tile_master.origin[0:2]]
            new_ref_allow_edge = (allow_edge[0] - inst_loc[0] - ref_x_min, allow_edge[1] - inst_loc[1] - ref_y_min, allow_edge[2] - inst_loc[0] - ref_x_min, allow_edge[3] - inst_loc[1] - ref_y_min )
            new_ref_allow_edge = dic_orientation_reversed[ self.dic_tiles[instance].inst_orient](new_ref_allow_edge[0:2]) + dic_orientation_reversed[ self.dic_tiles[instance].inst_orient](new_ref_allow_edge[2:])
            ref_edge = self.dic_inst2ref[instance][edge]
            self.dic_tiles[instance].tile_master.allowedge[ref_edge] = new_ref_allow_edge
        
            for tile in reuse_list:
                new_inst_allow_edge = dic_orientation[self.dic_tiles[tile].inst_orient](new_ref_allow_edge[0:2]) + dic_orientation[ self.dic_tiles[tile].inst_orient](new_ref_allow_edge[2:])               
                inst_loc = self.dic_tiles[tile].inst_loc
                new_inst_allow_edge = (new_inst_allow_edge[0] + inst_loc[0] + ref_x_min, 
                                        new_inst_allow_edge[1] + inst_loc[1] + ref_y_min,
                                        new_inst_allow_edge[2] + inst_loc[0] + ref_x_min,
                                        new_inst_allow_edge[3] + inst_loc[1] + ref_y_min )
                self.dic_tiles[tile].allowedge[self.dic_ref2inst[tile][ref_edge]] = new_inst_allow_edge
        return 1

    def reset_edge(self, instance):
        '''
            Update by Jiaming
        '''
        if instance not in self.dic_tiles: return 0
        master = self.dic_inst2master[instance]
        for inst in self.dic_master2inst[master]:
            for edge in self.dic_tiles[inst].allowedge:
                self.dic_tiles[inst].allowedge[edge] = self.dic_tiles[inst].edges[edge]

    def parsedef(self,file="data/Floorplan/*/*.def.gz",read_from_pkl = False,pkl_name = 'getshape.pkl',chipname = 'uvd_minus_wrapper',side_mode = 'most_left',track_valid = {'Y':['M0','M2','M4','M6','M8','M10'],'X':['M1','M3','M5','M7','M9','M11','M13']}):
        """
        FILE="data/Floorplan/*/*def.gz"
        UNITS=2000
        """
        self.__params__(self.parsedef.__doc__)
        def_file = glob.glob(file)
        self.chipname = chipname
        regx_diearea = re.compile(r'DIEAREA (\(.*\)) ;')
        regx_design = re.compile(r'DESIGN (\S+) ;')
        regx_tuple = re.compile(r'\( (\S+ \S+) \)')
        regx_track =re.compile(r'TRACKS (Y|X) (\S+) DO (\S+) STEP (\S+) LAYER (M5|M6|M7|M8|M9|M10|M12|M13)')
        # - df_gc_tcdx_t15 df_gc_tcdx_0_t + FIXED ( 9252468 -2616000 ) FS ;
        regx_inst = re.compile(r'- (\S+) (\S+).*\( (.*) \) (\S+) ?;?')
        if len(def_file) <= 0:
            logging.error("No def was found, Please check %s" % file)
            exit(1)
        report_limit = 3
        if read_from_pkl:
            with mkdir(file_name = pkl_name, mode = 'rb',type = 'data') as file:
                def_file = []
                db = pickle.load(file)
                self.dic_inst2masterinfo = db['dic_inst2masterinfo']
                self.dic_tile2poly = db['dic_tile2poly']
                self.dic_tile2track= db['dic_tile2track']
                self.dic_tile2offset= db['dic_tile2offset']
        db = {}
        for file in def_file:
            if 'region' in file: continue
            if 'bbox' in file: continue
            if report_limit > 0:
                print file
                report_limit -= 1
            elif report_limit == 0:
                print "........"
                report_limit -= 1
            f = gzopen(file)
            for line in f:
                mt_design = regx_design.search(line)
                if mt_design:
                    tile = mt_design.groups()[0]
                    break
            if self.chipname  == tile:
                for line in f:
                    if 'END COMPONENTS' in line: break
                    mt_inst = regx_inst.search(line)
                    mt_diearea = regx_diearea.search(line)
                    if mt_diearea:
                        area = mt_diearea.groups()[0]
                        mt_tuple = regx_tuple.findall(area)
                        maxX,maxY = (0,0)
                        minX,minY = (0,0)   
                        for i in mt_tuple:
                            x,y = [int(j) for j in i.split()]
                            if x > maxX: maxX = x
                            if y > maxY: maxY = y
                            if x < minX: minX = x
                            if y < minY: minY = y
                    self.dic_tile2offset[self.chipname] = (0,0)
                    if mt_inst:
                        tmp = mt_inst.groups()
                        print >>self.LOG,'CHIP cells:',tmp
                        self.dic_inst2masterinfo[tmp[0]] = [tmp[1],(int(tmp[2].split()[0]),int(tmp[2].split()[1])),tmp[-1]]
                self.dic_inst2masterinfo[self.chipname] = [self.chipname,(minX,minY),'N']
                f.close()
                f = gzopen(file)
            track_info = defaultdict(list)
            for line in f:
                mt_design = regx_design.search(line)
                mt_diearea = regx_diearea.search(line)
                mt_track = regx_track.search(line)
                if mt_design:
                    tile = mt_design.groups()[0]
                    if tile in self.dic_tile2poly: break
                if mt_diearea:
                    area = mt_diearea.groups()[0]
                    print >>self.LOG,tile,area
                    mt_tuple = regx_tuple.findall(area)
                    if len(mt_tuple) != 2:
                        maxX,maxY = (0,0)
                        minX,minY = (0,0)
                        for i in mt_tuple:
                            x,y = [int(j) for j in i.split()]
                            if x > maxX: maxX = x
                            if y > maxY: maxY = y
                            if x < minX: minX = x
                            if y < minY: minY = y
                            
                            self.dic_tile2poly[tile].append((x,y))
                        print >>self.LOG,'J',self.dic_tile2poly[tile]
                        x_center,y_center = (maxX+minX)/2,(maxY+minY)/2 
                        if tile == self.chipname:x_center,y_center  = (0,0)
                        self.dic_tile2offset[tile] = (x_center,y_center)
                        for id in range(len(self.dic_tile2poly[tile])):
                            i = self.dic_tile2poly[tile][id]
                            self.dic_tile2poly[tile][id] = (i[0]-x_center,i[1]-y_center)
                        maxX,maxY = (0,0)
                        minX,minY = (0,0)
                        poly = self.dic_tile2poly[tile]
                        print >>self.LOG,'K',self.dic_tile2poly[tile]
                        for i in poly:
                            x,y = i
                            if x > maxX: maxX = x
                            if y > maxY: maxY = y
                            if x < minX: minX = x
                            if y < minY: minY = y
                        tmp_Y = [i for i in poly if i[1] == minY]
                        tmp_X = [i for i in poly if i[0] == minX]
                        minY_minX = tmp_Y[0][0]
                        minX_minY = tmp_X[0][1]

                        for loc in tmp_Y:
                            if loc[0] < minY_minX:
                                minY_minX = loc[0]
                        for loc in tmp_X:
                            if loc[1] < minX_minY:
                                minX_minY = loc[1]
                        bottom_left = (minY_minX,minY)    
                        most_left = (minX, minX_minY)
                        #judge clock wise or couter clock wise
                        d = 0
                        length = len(poly)
                        for i in range(length):
                            d += -0.5*(poly[(i+1)%length][1] + poly[i%length][1])*(poly[(i+1)%length][0] - poly[i%length][0])
                        if d > 0:#counter clockwise 
                            print >>self.LOG,"counter clockwise"
                            poly = list(reversed(poly))
                        else:
                            print >>self.LOG,"clockwise"    
                        if side_mode == 'most_left':
                            index = poly.index(most_left)
                        elif side_mode == 'bottom_left':
                            index = poly.index(bottom_left)
                        else:
                            print 'Error: Specify side mode, most left or bottom left as side 1'
                        print >>self.LOG,poly,index
                        poly_new = poly[index:] + poly[0:index]
                        print >>self.LOG,poly_new
                        self.dic_tile2poly[tile] = poly_new
                    elif len(mt_tuple) == 2:
                        #change bbox to clockwise polygon if diearea is bbox type
                        x0,y0 = [int(j) for j in mt_tuple[0].split()]
                        x1,y1 = [int(j) for j in mt_tuple[1].split()]
                        x_center,y_center = (x0+x1)/2,(y0+y1)/2
                        if tile == self.chipname:x_center,y_center   = (0,0)
                        self.dic_tile2offset[tile] = (x_center,y_center)
                        self.dic_tile2poly[tile].append((x0-x_center,y0-y_center))
                        self.dic_tile2poly[tile].append((x0-x_center,y1-y_center))
                        self.dic_tile2poly[tile].append((x1-x_center,y1-y_center))
                        self.dic_tile2poly[tile].append((x1-x_center,y0-y_center))
                        print >>self.LOG,'K',self.dic_tile2poly[tile]
                if mt_track:
                    #self.pitch = {'M4':[('Y','start','do','pitch')],'M5':[('start','do','pitch')]}}
                    track, start, do, step, layer = mt_track.groups()
                    if layer not in track_valid[track]:continue
                    track_info[layer].append([track,int(start),int(do),int(step)])
                if 'PINS' in line or 'COMPONENTMASKSHIFT' in line:
                    self.dic_tile2track[tile] = track_info
                    break
            f.close()
        db['dic_tile2track'] =    self.dic_tile2track
        db['dic_tile2poly'] = self.dic_tile2poly
        db['dic_inst2masterinfo'] = self.dic_inst2masterinfo
        db['dic_tile2offset'] = self.dic_tile2offset
        with mkdir(file_name = pkl_name, mode = 'wb',type = 'data') as file:
            pickle.dump(db,file)
        #Generate color for master tiles
        c = colors.colors()
        dic_master2color = {master : c.get_random_color() for master in self.dic_tile2poly}
        #Generate meta class for tile master
        dic_meta2tile = {}
        self.dic_master2edgeside = defaultdict(dict)
        for master in dic_master2color:
            ref_poly = np.array(self.dic_tile2poly.get(master,[[-5,-5],[5,-5],[5,5],[-5,5]]))
            shape = ref_poly.shape[0]
            edges = {} #store edges
            #The left edge of a rectangular shape, or the lower left-most vertical edge of a rectilinear shape, is side number
            #1. The side numbers increment as you proceed clockwise around the shape
            edgeside = {} #store edge
            v = h = 0
            for p  in range(shape):
                edge_key = (ref_poly[p%shape][0],ref_poly[p%shape][1],ref_poly[(p+1)%shape][0],ref_poly[(p+1)%shape][1])
                edges[edge_key] = edge_key
                edgeside[edge_key] = p + 1 
            self.dic_master2edgeside[master] = edgeside
            x_min, y_min = ref_poly.min(axis = 0)
            x_max, y_max = ref_poly.max(axis = 0)
            origin = (x_min, y_min, x_max, y_max )
            dic_meta2tile[master] = type(master,(),{'edges':edges,
                                                    'allowedge':edges,
                                                    'ref_name':master,
                                                    'color':dic_master2color[master],
                                                    'ref_poly':ref_poly,
                                                    'origin':origin,
                                                    'track':self.dic_tile2track[master],
                                                    'edgeside':edgeside,
                                                    'offset':self.dic_tile2offset[master],
                                                    })

        #Generate class for chip
        #CHIP->Master->Instance
        for inst in  self.dic_inst2masterinfo: 
            master = self.dic_inst2masterinfo[inst][0]
            if master not in self.dic_tile2poly: continue
            self.dic_tiles[inst] = Tile_Instance(dic_meta2tile[master])
            self.dic_tiles[inst].inst_name = inst
            self.dic_tiles[inst].inst_loc = self.dic_inst2masterinfo[inst][1]
            self.dic_tiles[inst].inst_orient = self.dic_inst2masterinfo[inst][2]
            x_min, y_min, x_max, y_max = self.dic_tiles[inst].tile_master.origin
            self.dic_tiles[inst].inst_size = (x_max - x_min, y_max - y_min)
            if self.dic_tiles[inst].inst_orient in dic_legal:
                tmp1 = np.array([[abs(x_min) + self.dic_tiles[inst].inst_loc[0], abs(y_min) + self.dic_tiles[inst].inst_loc[1]] for i in range(self.dic_tiles[inst].tile_master.ref_poly.shape[0])])
            else:
                tmp1 = np.array([[abs(y_min) + self.dic_tiles[inst].inst_loc[0], abs(x_min) + self.dic_tiles[inst].inst_loc[1]] for i in range(self.dic_tiles[inst].tile_master.ref_poly.shape[0])])
            tmp2 = np.array([dic_orientation[self.dic_tiles[inst].inst_orient](point) for point in self.dic_tiles[inst].tile_master.ref_poly])
            tmp = tmp1 + tmp2
            self.dic_tiles[inst].inst_poly =  tmp
            #generate edge relationship between instance and master tile
            tmp3 = np.array([point for point in self.dic_tiles[inst].tile_master.ref_poly])
            shape = tmp2.shape[0]
            self.dic_inst2ref[inst] ={ (tmp[p%shape][0],tmp[p%shape][1],tmp[(p+1)%shape][0],tmp[(p+1)%shape][1]):(tmp3[p%shape][0],tmp3[p%shape][1],tmp3[(p+1)%shape][0],tmp3[(p+1)%shape][1])for p in range(shape)}
            #reverse key & value
            self.dic_ref2inst[inst] = {v:k for k,v in self.dic_inst2ref[inst].items()}

    def plot2(self,special= []):
        from matplotlib.path import Path
        from matplotlib.patches import PathPatch
        import matplotlib.pyplot as plt
        from matplotlib import colors
        fig,ax = plt.subplots()
        for inst in self.dic_tiles:
            if self.dic_tiles[inst].inst_poly.shape[0] == 1: continue
            tmp = np.row_stack((self.dic_tiles[inst].inst_poly,np.array(self.dic_tiles[inst].inst_poly[0])))
            vertices = np.array(tmp ,float)
            codes = [Path.MOVETO] + [Path.LINETO]*(self.dic_tiles[inst].inst_poly.shape[0]-1) + [Path.CLOSEPOLY]
            path = Path(vertices, codes) 
            edgecolor = 'black' if inst in special else 'black'
            if len(special):
                if inst in special:
                    facecolor = 'blue'
                else:
                    facecolor = 'lightslategray'
                
            else:
                facecolor = self.dic_tiles[inst].tile_master.color 
            if inst == self.chipname:
                pathpatch = PathPatch(path,facecolor='None' ,edgecolor=edgecolor)
            else:
                pathpatch = PathPatch(path,facecolor=facecolor ,edgecolor=edgecolor)
            a,b = self.dic_tiles[inst].inst_poly[0]
            plt.text(a,b, inst, dict(size=15))
            
            ax.add_patch(pathpatch)
            #ax.dataLim.update_from_data_xy(vertices)
        ax.autoscale_view()
        plt.show()
    def plot_edge(self,master):
        from matplotlib.path import Path
        from matplotlib.patches import PathPatch
        from matplotlib.lines import Line2D
        import matplotlib.pyplot as plt
        from matplotlib import colors
        fig,ax = plt.subplots()
        for inst in self.dic_tiles:
                
            if self.dic_tiles[inst].inst_poly.shape[0] == 1: continue
            tmp = np.row_stack((self.dic_tiles[inst].inst_poly,np.array(self.dic_tiles[inst].inst_poly[0])))
            vertices = np.array(tmp ,float)
            codes = [Path.MOVETO] + [Path.LINETO]*(self.dic_tiles[inst].inst_poly.shape[0]-1) + [Path.CLOSEPOLY]
            path = Path(vertices, codes) 
            edgecolor = 'yellow'
            facecolor = 'lightslategray'
            if inst == self.chipname:
                pathpatch = PathPatch(path,facecolor='None' ,edgecolor=edgecolor)
            else:
                pathpatch = PathPatch(path,facecolor=facecolor ,edgecolor=edgecolor)
            ax.add_patch(pathpatch)
            #ax.dataLim.update_from_data_xy(vertices)
        for inst in self.dic_master2inst[master]:
            for edge in self.dic_tiles[inst].allowedge:
                line = self.dic_tiles[inst].allowedge[edge]
                line = [line[0:2],line[2:]]
                (x,y) = zip(*line)
                ax.add_line(Line2D(x,y,linewidth=2,color='red'))
        ax.autoscale_view()
        plt.show()
            
    def __del__(self):
        self.LOG.close()
        
    def getabuttile(self):
        """
        ####
        """
        dic_seg2tile = {}
        dic_seg2orign = {}
        for inst in self.dic_tiles:
            poly =    self.dic_tiles[inst].inst_poly
            polygon = Polygon(self.dic_tiles[inst].inst_poly)
            if poly.shape[0] <= 1: continue
            for p in range(poly.shape[0]):  
                edge = tuple(list(poly[p%poly.shape[0]]) + list(poly[(p+1)%poly.shape[0]]))
                if edge[0] == edge[2]:
                    rate = Point(edge[0] + 2,(edge[1] + edge[3])/2)
                    if rate.within(polygon):
                        dic_seg2orign[edge] =  (edge[0] + 2,(edge[1] + edge[3])/2)
                    else:
                        dic_seg2orign[edge] =  (edge[0] - 2,(edge[1] + edge[3])/2)
                else:
                    rate = Point((edge[0] + edge[2])/2,edge[1] + 2)
                    if rate.within(polygon):
                        dic_seg2orign[edge] =  ((edge[0] + edge[2])/2,edge[1] + 2)
                    else:
                        dic_seg2orign[edge] =  ((edge[0] + edge[2])/2,edge[1] - 2)
                dic_seg2tile[edge] = inst
                
                self.dic_tiles[inst].edges[edge] = edge
                self.dic_tiles[inst].allowedge[edge] = edge
        #space = min([min(abs(i[2]-i[0]),abs(i[3]-i[1])) for i in  dic_seg2tile])
        #print "Func getabuttile:Space used to identify whether abut or not:",space,'um...'
        vert_lines = []
        hori_lines = []
        for seg in dic_seg2tile:
            if seg[0] == seg[2]:
                vert_lines.append(seg)
            else:
                hori_lines.append(seg)
        #find  abut tiles
        for seg in dic_seg2tile:
            #f = 1 if seg == (-16356492, 23414640, -16356492, 2726640) else 0
            #f = 1 if dic_seg2tile[seg] == 'gfx' else 0
            #if f: print '###',seg
            if seg[0] == seg[2]:    
                range_min,range_max = sorted([seg[1],seg[3]])
                range_min =   (range_min/2000+1)*2000
                range_max = range_max 
                #tmp = filter( lambda f: abs(f[0] - seg[0]) < space, [ i for i in vert_lines if max(i[1::2]) > min(seg[1::2]) and max(seg[1::2]) > min(i[1::2]) ])
                tmp = [ i for i in vert_lines if max(i[1::2]) > min(seg[1::2]) and max(seg[1::2]) > min(i[1::2]) ]

                seg_point = set(range(range_min,range_max,2000))
                tmp = sorted(tmp,key = lambda x: (x[0],dic_seg2orign[x][0]))
                index = tmp.index(seg)
                for l in range(index-1,-1,-1):   
                    flag = len(seg_point)
                    range_min_tmp,range_max_tmp = sorted([tmp[l][1],tmp[l][3]])
                    range_min_tmp = (range_min_tmp/2000+1)*2000
                    range_max_tmp = range_max_tmp 
                    tmp_point = set(range(range_min_tmp,range_max_tmp,2000))
                    abut_point = seg_point & tmp_point
                    seg_point -= tmp_point
                    
                    if len(seg_point) != flag:
                        abut_point = (0,min(abut_point),max(abut_point))
                        #if f: print 1, dic_seg2tile[tmp[l]],len(seg_point),flag,abut_point
                        self.dic_tiles[dic_seg2tile[seg]].abut_inst.append((seg, tmp[l], dic_seg2tile[tmp[l]],abut_point)) 
                seg_point = set(range(range_min,range_max,2000))
                for r in range(index+1,len(tmp)):
                    flag = len(seg_point)
                    range_min_tmp,range_max_tmp = sorted([tmp[r][1],tmp[r][3]])
                    range_min_tmp = (range_min_tmp/2000+1)*2000
                    range_max_tmp = range_max_tmp 
                    tmp_point = set(range(range_min_tmp,range_max_tmp,2000))
                    abut_point = seg_point & tmp_point
                    seg_point -= tmp_point
                    

                    #data structure      segment:(abut segment, tile name)
                    if len(seg_point) != flag:
                        abut_point = (0,min(abut_point),max(abut_point))
                        self.dic_tiles[dic_seg2tile[seg]].abut_inst.append((seg, tmp[r], dic_seg2tile[tmp[r]],abut_point))
            else:
                #tmp = filter( lambda f: abs(f[1] - seg[1]) < space, [ i for i in vert_lines if max(i[0::2]) > min(seg[0::2]) and max(seg[0::2]) > min(i[0::2]) ])
                range_min,range_max = sorted([seg[0],seg[2]])
                range_min = (range_min/2000+1)*2000
                range_max = range_max 
                tmp = [ i for i in hori_lines if max(i[0::2]) > min(seg[0::2]) and max(seg[0::2]) > min(i[0::2]) ]
                seg_point = set(range(range_min,range_max,2000))
                tmp = sorted(tmp,key = lambda x: (x[1],dic_seg2orign[x][1]))
                index = tmp.index(seg)
                for b in range(index-1,-1,-1):   
                    flag = len(seg_point)
                    range_min_tmp,range_max_tmp = sorted([tmp[b][0],tmp[b][2]])
                    range_min_tmp = (range_min_tmp/2000+1)*2000
                    range_max_tmp = range_max_tmp 
                    tmp_point = set(range(range_min_tmp,range_max_tmp,2000) )
                    abut_point = seg_point & tmp_point
                    seg_point -= tmp_point
                    if len(seg_point) != flag:
                        abut_point = (1,min(abut_point),max(abut_point))
                        self.dic_tiles[dic_seg2tile[seg]].abut_inst.append((seg, tmp[b], dic_seg2tile[tmp[b]],abut_point))
                seg_point = set(range(range_min,range_max,2000))
                for t in range(index+1,len(tmp)):
                    flag = len(seg_point)
                    range_min_tmp,range_max_tmp = sorted([tmp[t][0],tmp[t][2]])
                    range_min_tmp = (range_min_tmp/2000+1)*2000
                    range_max_tmp = range_max_tmp 
                    tmp_point = set(range(range_min_tmp,range_max_tmp,2000))
                    abut_point = seg_point & tmp_point
                    seg_point -= tmp_point
                    

                    #data structure      segment:(abut segment, tile name)
                    if len(seg_point) != flag:
                        abut_point = (1,min(abut_point),max(abut_point))
                        self.dic_tiles[dic_seg2tile[seg]].abut_inst.append((seg, tmp[t], dic_seg2tile[tmp[t]],abut_point))

class get_blockage(object):
    def __init__(self,shape,tune = 'kkong/tcls/blockages/*.tcl'):   
        self.dic_master2bkg = defaultdict(dict)
        self.dic_inst2bkg = defaultdict(dict)
        self.shape = shape
        self.get_blockage(tune = tune)
        self.transfer2instance()
        self.update_blkedge()
        self.chipname = self.shape.chipname
    def transfer2instance(self):
        for master in self.dic_master2bkg:
            for dir in self.dic_master2bkg[master]:
                for boundary in self.dic_master2bkg[master][dir]:
                    tmp = []
                    x_center,y_center = self.shape.dic_tile2offset[master]
                    for loc in boundary:
                        a = loc[0] - x_center
                        b = loc[1] - y_center
                        tmp.append((a,b))

                    for inst in self.shape.dic_master2inst[master]:
                        x_min, y_min, x_max, y_max = self.shape.dic_tiles[inst].tile_master.origin
                        tmp1 = np.array([[abs(x_min) + self.shape.dic_tiles[inst].inst_loc[0], abs(y_min) + self.shape.dic_tiles[inst].inst_loc[1]] for i in range(2)])
                        tmp2 = np.array([dic_orientation[self.shape.dic_tiles[inst].inst_orient](point) for point in tmp])
                        tmp3 = tmp1 + tmp2
                        if inst in self.dic_inst2bkg and dir in self.dic_inst2bkg[inst]:
                            self.dic_inst2bkg[inst][dir].append(tmp3)
                        else:
                            self.dic_inst2bkg[inst][dir] = [tmp3]
                        
    def update_blkedge(self):
        RPT = mkdir_open('getshape/update_blkedge.rpt',mode = 'w+')
        for inst in self.dic_inst2bkg:
            print >>RPT,inst,self.shape.dic_tiles[inst].abut_inst
            for dir in self.dic_inst2bkg[inst]:
                #abut_list = [abut for abut in self.shape.dic_tiles[inst].abut_inst if abut[-1][0] == dir and inst != abut[2]]
                for boundary in self.dic_inst2bkg[inst][dir]:
                    abut_list = [abut for abut in self.shape.dic_tiles[inst].abut_inst if abut[-1][0] == dir and inst != abut[2]]
                    a,b = boundary[0],boundary[1]
                    x_y = (dir+1)%2
                    length = sorted([a[x_y],b[x_y]])
                    space = sorted([a[dir],b[dir]])
                    for edge in abut_list:
                        edge_xy = edge[0][dir]
                        method  = 0
                        if edge_xy < space[1] and edge_xy > space[0]:
                            abut_edge = edge[-1]
                            if length[1] <= abut_edge[1] or length[0] > abut_edge[2]:
                                continue
                            elif length[1] > abut_edge[2] and length[0] > abut_edge[1]:
                                abut_edge_new = list(abut_edge)
                                abut_edge_new[2] = length[0]/2000*2000
                                if edge in self.shape.dic_tiles[inst].abut_inst:
                                    self.shape.dic_tiles[inst].abut_inst.remove(edge)
                                edge_new = list(edge)
                                edge_new[-1] = tuple(abut_edge_new)
                                self.shape.dic_tiles[inst].abut_inst.append(tuple(edge_new))
                                print >>RPT,'#1',inst,edge,edge_new
                            elif length[1] < abut_edge[2] and length[0] < abut_edge[1]:
                                abut_edge_new = list(abut_edge)
                                abut_edge_new[1] = length[1]/2000*2000
                                if edge in self.shape.dic_tiles[inst].abut_inst:self.shape.dic_tiles[inst].abut_inst.remove(edge)
                                edge_new = list(edge)
                                edge_new[-1] = tuple(abut_edge_new)
                                print >>RPT,'#1',inst,edge,edge_new
                                self.shape.dic_tiles[inst].abut_inst.append(tuple(edge_new))
                            elif length[1] >= abut_edge[2] or length[0] < abut_edge[1]:
                                if edge in self.shape.dic_tiles[inst].abut_inst:
                                    self.shape.dic_tiles[inst].abut_inst.remove(edge)
                                method = 1
                                print >>RPT,'#1',inst,edge,'Remove'
                            elif length[1] <= abut_edge[2] or length[0] >= abut_edge[1]:
                                print >>RPT,'Error: blk not meet requirement',inst,boundary
                                continue
                        else:
                            continue

                        abut_tile = edge[2]
                        for edge2 in self.shape.dic_tiles[abut_tile].abut_inst:
                            if edge2[2] == inst and edge2[-1] == abut_edge:
                                self.shape.dic_tiles[abut_tile].abut_inst.remove(edge2)
                                if method == 0:
                                    edge2_new =list(edge2)
                                    edge2_new[-1] = tuple(abut_edge_new)
                                    self.shape.dic_tiles[abut_tile].abut_inst.append(tuple(edge2_new))
                                    print >>RPT,'#2',abut_tile,edge,edge2_new
                                else:
                                    print >>RPT,'#2',abut_tile,edge2,'remove'
            print >>RPT,inst,self.shape.dic_tiles[inst].abut_inst
        RPT.close()                
                        

    def get_blockage(self,tune = 'kkong/tcls/blockages/*_bkg.tcl'):
        pt_design = re.compile(r'.*/(\S+)_bkg.*\.tcl')
        pt_layer = re.compile(r'-layers {(.*?)}')
        pt_boundary = re.compile(r'-boundary\s+{\s*{(.*)}\s*{(.*)}\s*}')
        for file in glob.glob(tune):
            mt_design = pt_design.search(file)
            if mt_design:
                design = mt_design.groups()[0]
            else:
                continue
            full_line = ''
            with open(file,'r+') as f:
                tmp_dict =defaultdict(list)
                for line in f:
                    if '\\' in line:
                        full_line += line.strip()
                        full_line = full_line.strip('\\')
                        continue
                    else:
                        if full_line:
                            line = full_line + line
                            full_line = ''

                    if 'create_pin_blockage' not in line:
                        full_line = ''
                        continue
                    mt_layer = pt_layer.search(line)
                    mt_boundary = pt_boundary.search(line)
                    if mt_layer:
                        layers = mt_layer.groups()[0]
                    if mt_boundary:
                        boundary = mt_boundary.groups()
                        boundary = ([int(float(i)*2000) for i in boundary[0].split()],[int(float(i)*2000) for i in boundary[1].split()])
                    if 'M6' in layers:
                        tmp_dict[0].append(boundary)
                    else:
                        tmp_dict[1].append(boundary)
            self.dic_master2bkg[design].update( tmp_dict )

    def plot(self):
        from matplotlib.path import Path
        from matplotlib.patches import PathPatch
        import matplotlib.pyplot as plt
        fig,ax = plt.subplots()
        for inst in self.shape.dic_tiles:
            if self.shape.dic_tiles[inst].inst_poly.shape[0] == 1: continue
            tmp = np.row_stack((self.shape.dic_tiles[inst].inst_poly,np.array(self.shape.dic_tiles[inst].inst_poly[0])))
            vertices = np.array(tmp ,float)
            codes = [Path.MOVETO] + [Path.LINETO]*(self.shape.dic_tiles[inst].inst_poly.shape[0]-1) + [Path.CLOSEPOLY]
            path = Path(vertices, codes) 
            edgecolor = 'black'
            facecolor = 'lightslategray'
            if inst == self.chipname:
                pathpatch = PathPatch(path,facecolor='None' ,edgecolor=edgecolor)
            else:
                pathpatch = PathPatch(path,facecolor=facecolor ,edgecolor=edgecolor)
            #a,b = self.dic_tiles[inst].inst_poly[0]
            #plt.text(a,b, inst, dict(size=15))
            ax.add_patch(pathpatch)
        for inst in self.dic_inst2bkg:
            for dir in self.dic_inst2bkg[inst]:
                for boundary in self.dic_inst2bkg[inst][dir]:
                    x0,y0 = boundary[0]
                    x1,y1 = boundary[1]
                    tmp0 = []
                    tmp0.append([x0,y0])
                    tmp0.append([x0,y1])
                    tmp0.append([x1,y1])
                    tmp0.append([x1,y0])
                    inst_poly = np.array(tmp0)
                    tmp = np.row_stack((inst_poly,np.array(inst_poly[0])))
                    vertices = np.array(tmp ,float)
                    codes = [Path.MOVETO] + [Path.LINETO]*(inst_poly.shape[0]-1) + [Path.CLOSEPOLY]
                    path = Path(vertices, codes) 
                    edgecolor = 'red' 
                    if dir:
                        facecolor = 'blue'
                    else:
                        facecolor = 'green'
                    
                    pathpatch = PathPatch(path,facecolor=facecolor ,edgecolor=edgecolor)
                    ax.add_patch(pathpatch)

            #ax.dataLim.update_from_data_xy(vertices)
        ax.autoscale_view()
        plt.savefig('%s/rpt/getshape/bkg.png' % os.popen("whoami").readlines()[0].strip(),dpi = 500)
        #plt.show()

    def plot_edge(self):
        from matplotlib.path import Path
        from matplotlib.patches import PathPatch
        import matplotlib.pyplot as plt
        from matplotlib.lines import Line2D
        fig,ax = plt.subplots()

        
        for inst in self.shape.dic_tiles:
                
            if self.shape.dic_tiles[inst].inst_poly.shape[0] == 1: continue
            tmp = np.row_stack((self.shape.dic_tiles[inst].inst_poly,np.array(self.shape.dic_tiles[inst].inst_poly[0])))
            vertices = np.array(tmp ,float)
            codes = [Path.MOVETO] + [Path.LINETO]*(self.shape.dic_tiles[inst].inst_poly.shape[0]-1) + [Path.CLOSEPOLY]
            path = Path(vertices, codes) 
            edgecolor = 'yellow'
            facecolor = 'white'
            if inst == self.chipname:
                pathpatch = PathPatch(path,facecolor='None' ,edgecolor=edgecolor)
            else:
                pathpatch = PathPatch(path,facecolor=facecolor ,edgecolor=edgecolor)
            ax.add_patch(pathpatch)
        c = colors.colors()
        for inst in self.dic_inst2bkg:
            
            for edge in self.shape.dic_tiles[inst].abut_inst:
                if edge[2] == inst:continue
                abut_edge = edge[-1]
                if abut_edge[0]:
                    line = (abut_edge[1],edge[0][1],abut_edge[2],edge[0][3])
                else:
                    line = (edge[0][0],abut_edge[1],edge[0][2],abut_edge[2])
                line = [line[0:2],line[2:]]
                (x,y) = zip(*line)
                ax.add_line(Line2D(x,y,linewidth=1.5,color=c.get_random_color()))
        ax.autoscale_view()
        plt.savefig('%s/rpt/getshape/avail_edge.png' % os.popen("whoami").readlines()[0].strip(),dpi=500)
        plt.show()





if __name__ == "__main__":
    import datetime
    begin = datetime.datetime.now()
    tmp = getshape()
    tmp.parsedef(file="kkong/data/placecollapsepins/*/*.prepin.def.gz",read_from_pkl = True,chipname = 'reuse_wrapper')
    #tmp.parsedef(file="data/CollapseFeedThruReuse/*/*.def.gz",read_from_pkl = False,chipname = 'CHIP')
    tmp.getReuse()
    tmp.getabuttile()
    tmp.sortabutlistbycommonedge()
    tmp.filter_edge()
    tmp.checkabut()
    tmp.plot2()
    bkg = get_blockage(tmp,tune = 'kkong/tcls/blockages/*.tcl')
    bkg.plot()
    bkg.plot_edge()
    end = datetime.datetime.now()
    print  end-begin
    
    

import pandas as pd
import numpy as np
import jenkspy
from brix import Indicator

class Giants(Indicator):
    '''
    Indicator that simulates the benefit that university researchers get from being in close proximity to private R&D.
    User can change location of academic departments and of private R&D labs, and the module will compute the research output of academia and display it as the height of each cell.

    color_method can be 'jenks', 'quantile', or 'none'
    '''
    def setup(self,quietly=True,color_method='jenks'):
        self.quietly = quietly
        if not self.quietly:
            print('Setting up indicator')
        self.dis = None
        self.local_crs = 'ESRI:102008'
        self.name = 'Knowledge spillovers'
        self.indicator_type = 'grid'
        self.override_verification = True
        self.requires_geometry = True
        
        self.gamma = 0.004
        self.beta0 = 0.000
        self.beta1 = 0.06
        
        self.color_method = color_method
        
        self.scale = 2
        self.background_alpha = 0.5
        self.units_alpha = 0.9
        
        self.base_height = 8
        
        self.academic_types = set(['Academic'])
        self.private_types  = set(['Private R&D'])
        
        self.n_colors = 3
        self.breaks = None
        self.color_palette = None
        self.academic_color = None
        self.set_color_palette()

    def set_color_palette(self):
        '''
        Sets the color palette to be used according to self.n_colors
        '''
        self.Reds = {
            3: [(254,224,210), (252,146,114), (222,45,38)],
            4: [(254,229,217), (252,174,145), (251,106,74), (203,24,29)],
            5: [(254,229,217), (252,174,145), (251,106,74), (222,45,38), (165,15,21)],
            6: [(254,229,217), (252,187,161), (252,146,114), (251,106,74), (222,45,38), (165,15,21)],
            7: [(254,229,217), (252,187,161), (252,146,114), (251,106,74), (239,59,44), (203,24,29), (153,0,13)],
            8: [(255,245,240), (254,224,210), (252,187,161), (252,146,114), (251,106,74), (239,59,44), (203,24,29), (153,0,13)],
            9: [(255,245,240), (254,224,210), (252,187,161), (252,146,114), (251,106,74), (239,59,44), (203,24,29), (165,15,21), (103,0,13)]
        }

        color_palette = self.Reds[self.n_colors]
        self.color_palette = [list(c) for c in color_palette]

    def set_academic_color(self,geogrid_data):
        '''
        Sets the default color of academic deparments according to GEOGRID.
        '''
        if self.academic_color is None:
            hex_color = geogrid_data.get_geogrid_props()['types']['Academic']['color'].replace('#','')
            self.academic_color = list(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
        
    def make_dis_df(self,geogrid_data):
        '''
        Initialize a dataframe with distances between all pairs of cells.
        This takes a bit, but makes updates run faster.
        '''
        if not self.quietly:
            print('Calculating distances between cells (may take a bit)')
        geogrid_data_df = geogrid_data.as_df()
        dis = geogrid_data_df[['id','geometry']]
        dis = dis.to_crs(self.local_crs)
        dis.geometry = dis.geometry.centroid
        dis['flag'] = 1
        dis = pd.merge(dis,dis,on='flag').drop('flag',1)
        dis = dis[dis['id_x']!=dis['id_y']]
        dis['distance'] = [x.distance(y) for x,y in dis[['geometry_x','geometry_y']].values]
        self.dis = dis[['id_x','id_y','distance']]
        
    def return_indicator(self,geogrid_data):
        '''
        Returns the geogrid_data object to be posted to cityio.
        '''
        if self.dis is None:
            self.make_dis_df(geogrid_data)
        self.set_academic_color(geogrid_data)
        final_height_lookup = self.propagate_spillovers(geogrid_data)
        self.set_breaks(final_height_lookup)
        
        for cell in geogrid_data:
            if cell['id'] in final_height_lookup.keys():
                h = final_height_lookup[cell['id']]
                cell['height'] = self.scale*min([1000,h])
                cell['color'] = self.get_color(h)
            elif cell['name'] == 'Default':
                cell['height'] = 0
            else:
                cell['height'] = self.scale*self.base_height

            if cell['name']=='Default':
                cell['color'] = cell['color'][:3]+[int(self.background_alpha*255)]
            else:
                cell['color'] = cell['color'][:3]+[int(self.units_alpha*255)]
            if 'geometry' in cell.keys():
                del cell['geometry']
        return geogrid_data

    def propagate_spillovers(self,geogrid_data):
        '''
        Main function of the indicator.
        Calculates exposures and uses the model parameters to simulate the effect on university research.
        Returns a dictionary with cell ids as keys and the simulated research output as values.
        '''
        if not self.quietly:
            print('Propagating spillovers')
        geogrid_data_df = geogrid_data.as_df()
        geogrid_data_df.loc[geogrid_data_df['name'].isin(set(self.academic_types|self.private_types)),'height'] = self.base_height

        academic = geogrid_data_df[geogrid_data_df['name'].isin(self.academic_types)]
        private  = geogrid_data_df[geogrid_data_df['name'].isin(self.private_types)]

        exp = pd.merge(self.dis,private[['id','height']].rename(columns={'id':'id_y','height':'patents'}))
        exp['exp'] = np.exp(-self.gamma*exp['distance'])*exp['patents']
        exp = exp.groupby('id_x').sum()[['exp']].reset_index().rename(columns={'id_x':'id'})
        exp.loc[exp['exp']>50,'exp'] = 50

        academic = pd.merge(academic,exp)
        academic['final'] = academic['height']*np.exp(self.beta0+self.beta1*academic['exp'])
        final_height_lookup = dict(academic[['id','final']].values)
        return final_height_lookup

    def set_breaks(self,final_height_lookup):
        '''
        Sets the breaks to be used to color cells.
        '''
        if len(final_height_lookup)>0:
            if self.color_method == 'jenks':
                breaks = jenkspy.jenks_breaks(final_height_lookup.values(), nb_class=self.n_colors)
                self.breaks = np.array(breaks)
            elif self.color_method == 'quantile':
                breaks = [np.quantile(list(final_height_lookup.values()),q) for q in np.linspace(0,1,self.n_colors+1)]
                self.breaks = np.array(breaks)
            else:
                self.breaks = None
        else:
            self.breaks = None
    
    def get_color(self,h):
        '''
        Returns the color for height h according to self.breaks (see self.set_breaks)
        '''
        if self.breaks is not None:
            cat = min(min(np.where(self.breaks>=h)))
            cell_color = self.color_palette[cat-1]
        else:
            cell_color = self.academic_color
        return cell_color

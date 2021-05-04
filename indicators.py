import pandas as pd
import numpy as np
from brix import Indicator

class Giants(Indicator):
    '''
    Indicator that simulates the benefit that university researchers get from being in close proximity to private R&D.
    User can change location of academic departments and of private R&D labs, and the module will compute the research output of academia and display it as the height of each cell.
    '''
    def setup(self,quietly=True):
        self.quietly = quietly
        if not self.quietly:
            print('Setting up indicator')
        self.dis = None
        self.local_crs = 'ESRI:102008'
        self.name = 'Knowledge spillovers'
        self.indicator_type = 'grid'
        
        self.gamma = 0.004
        self.beta0 = 0.000
        self.beta1 = 0.06
        self.scale = 2
        
        self.background_alpha = 0.5
        self.units_alpha = 0.9
        
        self.base_height = 8
        
        self.academic_types = set(['Academic'])
        self.private_types  = set(['Private R&D'])
        
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
        final_height_lookup = self.propagate_spillovers(geogrid_data)
        for cell in geogrid_data:
            if cell['id'] in final_height_lookup.keys():
                cell['height'] = self.scale*min([1000,final_height_lookup[cell['id']]])
            elif cell['name'] == 'Default':
                cell['height'] = 0
            else:
                cell['height'] = self.scale*self.base_height
            if cell['name']=='Default':
                cell['color'] = cell['color'][:3]+[int(self.background_alpha*255)]
            else:
                cell['color'] = cell['color'][:3]+[int(self.units_alpha*255)]
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

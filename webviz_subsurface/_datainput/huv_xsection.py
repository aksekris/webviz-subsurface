import xtgeo
import pandas as pd
import numpy as np
import numpy.ma as ma
from pathlib import Path
from operator import add
from operator import sub


class HuvXsection:
    def __init__(
            self,
            surface_attributes: dict = None,
            zonation_data = None,
            conditional_data = None,
            fence = None,
            well_attributes = None,
    ):
        self.fence = fence
        self.surface_attributes = surface_attributes
        self.zonation_data = zonation_data
        self.conditional_data = conditional_data
        self.well_attributes = well_attributes
    
    def create_well(self, wellpath,surfacepaths):
        if not wellpath==None:
            well = xtgeo.Well(Path(wellpath))
            well_fence = well.get_fence_polyline(nextend=100, sampling=5)
            self.fence = well_fence
            well_df = well.dataframe
            well.create_relative_hlen()
            zonation_points = find_zone_RHLEN(well_df,well.wellname,self.zonation_data)
            conditional_points = find_conditional_RHLEN(well_df,well.wellname,self.conditional_data)
            color_list = ["rgb(245,245,245)"]
            for sfc in self.surface_attributes:
                color_list.append(self.surface_attributes[Path(sfc)]["color"])
            zonelog = plot_well_zonelog(well_df,color_list)
            self.well_attributes = {"well_df":well_df,"zonelog":zonelog,"zonation_points":zonation_points,"conditional_points":conditional_points}

    def get_plotly_well_data(self):
        if self.well_attributes ==None:
            return []
        else:
            data = [{"type": "line",
            "y": self.well_attributes["well_df"]["Z_TVDSS"],
            "x": self.well_attributes["well_df"]["R_HLEN"],
            "name": "well",
            "line": {"width": 7, "color": "black"},
            "fillcolor": "black",
            }]
            data += self.well_attributes["zonelog"]
            data += [{"mode": "markers",
                    "y": self.well_attributes["zonation_points"][1],
                    "x": self.well_attributes["zonation_points"][0],
                    "name": "zonation points",
                    "marker":{"size":5,"color":"black"}
            }]
            data += [{"mode": "markers",
                    "y": self.well_attributes["conditional_points"][1],
                    "x": self.well_attributes["conditional_points"][0],
                    "name": "conditional points",
                    "marker":{"size":5,"color":"rgb(30,144,255)"}
            }]
            return data

    def set_surface_lines(self, surfacepaths):
        for sfc_path in surfacepaths:
            sfc = xtgeo.surface_from_file(Path(sfc_path), fformat="irap_binary")
            sfc_line = sfc.get_randomline(self.fence)
            self.surface_attributes[Path(sfc_path)]['surface_line'] = sfc_line
            self.surface_attributes[Path(sfc_path)]['surface_line_xdata'] = sfc_line[:,0]
            self.surface_attributes[Path(sfc_path)]['surface_line_ydata'] = sfc_line[:,1]
    
    def set_error_lines(self, errorpaths):
        for sfc_path in self.surface_attributes:
            de_surface = xtgeo.surface_from_file(self.surface_attributes[Path(sfc_path)]["error_path"], fformat="irap_binary")
            de_line = de_surface.get_randomline(self.fence)
            sfc_line_ydata = self.surface_attributes[Path(sfc_path)]['surface_line_ydata']
            de_line_add = list(map(add, sfc_line_ydata, de_line[:,1])) #add error y data
            de_line_sub = list(map(sub, sfc_line_ydata, de_line[:,1])) #add error y data
            self.surface_attributes[Path(sfc_path)]["error_line_add"] = de_line_add
            self.surface_attributes[Path(sfc_path)]["error_line_sub"] = de_line_sub               

    def get_plotly_layout(self,surfacepaths:list):
        ymin, ymax = self.surfline_max_min_depth(surfacepaths)
        layout ={}
        if self.well_attributes == None:
            layout.update({
                "yaxis":{
                    "title":"Depth (m)",
                    "range":[ymax,ymin],
                },
                "xaxis": {
                    "title": "Distance from polyline",
                },
                "plot_bgcolor":'rgb(233,233,233)',
                "showlegend":False,
                "height": 830,
            })
        else:
            x_well, y_well, x_well_max, y_width,x_width = find_where_it_crosses_well(self.well_attributes["well_df"],ymin,ymax)
            layout.update({
                "yaxis":{
                    "title":"Depth (m)",
                    "autorange": "off",
                    "range" : [ymax,y_well-0.15*y_width],
                },
                "xaxis":{
                    "title": "Distance from polyline",
                    "range": [x_well-0.5*x_width,x_well_max+0.5*x_width],
                },
                "plot_bgcolor":'rgb(233,233,233)',
                "showlegend":False,
                "height": 830,
            })
        return layout

    def get_plotly_data(self, surface_paths:list, error_paths:list):

        min, max = self.surfline_max_min_depth(surface_paths)
        first_surf_line = self.surface_attributes[Path(surface_paths[0])]['surface_line']
        surface_tuples =[
            (sfc_path ,self.surface_attributes[Path(sfc_path)]['surface_line'])
            for sfc_path in surface_paths
        ]
        surface_tuples.sort(key=depth_sort, reverse=True)

        error_paths_iterateable = []
        error_sfc = []
        for error_path in error_paths:
            error_paths_iterateable.append(Path(error_path))

        for sfc_path in surface_paths:
            if self.surface_attributes[Path(sfc_path)]["error_path"] in error_paths_iterateable:
                self.surface_attributes[Path(sfc_path)]["error_line_add_plot"] = self.surface_attributes[Path(sfc_path)]["error_line_add"]
                self.surface_attributes[Path(sfc_path)]["error_line_sub_plot"] = self.surface_attributes[Path(sfc_path)]["error_line_sub"]
                error_sfc.append(Path(sfc_path))
        
        data = [ #Create helpline for bottom of plot
            {
                "type": "line",
                "x": [first_surf_line[0, 0], first_surf_line[np.shape(first_surf_line)[0] - 1, 0]],
                "y": [max + 50, max + 50],
                "line": {"color": "rgba(0,0,0,1)", "width": 0.6},
            }
        ]

        data +=[
            {
                'x':self.surface_attributes[Path(sfc_path)]['surface_line'][:,0],
                'y':self.surface_attributes[Path(sfc_path)]['surface_line'][:,1],
                'line': {"color": "rgba(0,0,0,1)", "width": 1},
                "fill": "tonexty",
                'fillcolor':self.surface_attributes[Path(sfc_path)]["color"]
            }
            for sfc_path, _ in surface_tuples
        ]

        data +=[
            {
                'x':self.surface_attributes[Path(sfc_path)]['surface_line'][:,0],
                'y':self.surface_attributes[Path(sfc_path)]["error_line_add_plot"],
                'line': {"color": "white", "width": 0.6},
            }
            for sfc_path in error_sfc
        ]

        data +=[
            {
                'x':self.surface_attributes[Path(sfc_path)]['surface_line'][:,0],
                'y':self.surface_attributes[Path(sfc_path)]['error_line_sub_plot'],
                'line': {"color": "black", "width": 0.6},
            }
            for sfc_path in error_sfc
        ]
        data+= self.get_plotly_well_data()

        return data


    def surfline_max_min_depth(self, surfacepaths:list):
        maxvalues = np.array([
            np.max(self.surface_attributes[Path(sfc_path)]['surface_line'][:,1])
            for sfc_path in surfacepaths
        ])
        minvalues = np.array([
            np.min(self.surface_attributes[Path(sfc_path)]['surface_line'][:,1])
            for sfc_path in surfacepaths
        ])
        return np.min(minvalues), np.max(maxvalues)


def depth_sort(elem):
    return np.min(elem[1][:, 1])

def plot_well_zonelog(well_df,color,zonelogname="Zonelog",zomin=-999):
    zvals = well_df["Z_TVDSS"].values.copy()
    hvals = well_df["R_HLEN"].values.copy()
    if zonelogname not in well_df.columns:
        return
    zonevals = well_df[zonelogname].values #values of zonelog
    zomin = (
        zomin if zomin >= int(well_df[zonelogname].min()) else int(well_df[zonelogname].min())
    ) #zomin=0 in this case
    zomax = int(well_df[zonelogname].max()) #zomax = 4 in this case
    # To prevent gaps in the zonelog it is necessary to duplicate each zone transition
    zone_transitions = np.where(zonevals[:-1] != zonevals[1:]) #index of zone transitions?
    for transition in zone_transitions:
        try:
            zvals = np.insert(zvals, transition, zvals[transition + 1])
            hvals = np.insert(hvals, transition, hvals[transition + 1])
            zonevals = np.insert(zonevals, transition, zonevals[transition])
        except IndexError:
            pass
    zoneplot = []
    for i, zone in enumerate(range(zomin, zomax + 1)):
        zvals_copy = ma.masked_where(zonevals != zone, zvals)
        hvals_copy = ma.masked_where(zonevals != zone, hvals)
        zoneplot.append({
            "x": hvals_copy.compressed(),
            "y": zvals_copy.compressed(),
            "line": {"width": 4, "color": color[i]},
            "fillcolor": color[i],
            "marker": {"opacity": 0.5},
            "name": f"Zone: {zone}",
        })
    return zoneplot


def find_zone_RHLEN(well_df,wellname,zone_path):
    zonation_data = pd.read_csv(zone_path[0])  #"/home/elisabeth/GitHub/Datasets/simple_model/output/log_files/zonation_status.csv")
    zone_df = zonation_data[zonation_data["Well"] == wellname]
    zone_df_xval = zone_df["x"].values.copy()
    zone_df_yval = zone_df["y"].values.copy()
    zone_RHLEN = np.zeros(len(zone_df_xval))
    for i in range(len(zone_df_xval)):
        well_df["XLEN"] = well_df["X_UTME"]-zone_df_xval[i]
        well_df["YLEN"] = well_df["Y_UTMN"]-zone_df_yval[i]
        well_df["SDIFF"] = np.sqrt(well_df.XLEN**2 + well_df.YLEN**2)
        index_array = np.where(well_df.SDIFF == well_df.SDIFF.min())
        zone_RHLEN[i] = well_df["R_HLEN"].values[index_array[0]][0]
    return np.array([zone_RHLEN,zone_df["TVD"]])

def find_conditional_RHLEN(well_df,wellname,cond_path):
    conditional_data = pd.read_csv(cond_path[0])   #"/home/elisabeth/GitHub/Datasets/simple_model/output/log_files/wellpoints.csv")
    cond_df = conditional_data[conditional_data["Well"] == wellname]
    cond_df_xval = cond_df["x"].values.copy()
    cond_df_yval = cond_df["y"].values.copy()
    cond_RHLEN = np.zeros(len(cond_df_xval))
    for i in range(len(cond_df_xval)):
        well_df["XLEN"] = well_df["X_UTME"]-cond_df_xval[i]
        well_df["YLEN"] = well_df["Y_UTMN"]-cond_df_yval[i]
        well_df["SDIFF"] = np.sqrt(well_df.XLEN**2 + well_df.YLEN**2)
        index_array = np.where(well_df.SDIFF == well_df.SDIFF.min())
        cond_RHLEN[i] = well_df["R_HLEN"].values[index_array[0]][0]
    return np.array([cond_RHLEN,cond_df["TVD"]])

def find_where_it_crosses_well(well_df,ymin,ymax):
    x_well_max = np.max(well_df["R_HLEN"])
    x_well = 0
    y_well = 0
    for i in range(len(well_df["Z_TVDSS"])):
        if well_df["Z_TVDSS"][i] >= ymin:
            y_well = well_df["Z_TVDSS"][i]
            x_well = well_df["R_HLEN"][i]
            break
    y_width = np.abs(ymax-y_well)
    x_width = np.abs(x_well_max-x_well)
    return x_well, y_well, x_well_max, y_width,x_width

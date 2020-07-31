import os
from uuid import uuid4
from pathlib import Path
import dash
import dash_table
import xtgeo
from dash.dependencies import Input, Output, State
import dash_html_components as html
import dash_core_components as dcc
import dash_bootstrap_components as dbc

import webviz_core_components as wcc
import webviz_subsurface_components
from webviz_config import WebvizPluginABC
from webviz_config.webviz_store import webvizstore

from .._datainput.surface import get_surface_layers
from .._datainput.well import get_well_layers
from .._datainput.huv_xsection import HuvXsection
from .._datainput.huv_table import FilterTable
from .._datainput import parse_model_file


class HorizonUncertaintyViewer(WebvizPluginABC):
    """ ### HorizonUncertaintyViewer
Visualizes depth error for surfaces in map view and cross section view.
The cross section is defined by wellfiles and surfacefiles or a polyline.
Polyline drawn interactivly in map view. Files parsed from model_file.xml.
* `basedir`: Path to folder with model_file.xml
   Make sure that the folder has the same format as a COHIBA folder
* `planned_wells_dir`: Path to folder with planned well files.
   Make sure that all planned wells have format 'ROXAR RMS well'.
"""

    # pylint: disable=too-many-locals
    def __init__(
        self, app, basedir: Path = None, planned_wells_dir: Path = None,
    ):

        super().__init__()
        self.plotly_theme = app.webviz_settings["theme"].plotly_theme
        self.uid = uuid4()
        self.set_callbacks(app)

        # Surfacefiles
        self.surfacefiles = parse_model_file.get_surface_files(basedir)
        surfacefiles_de = parse_model_file.get_surface_de_files(basedir)
        surfacefiles_dt = parse_model_file.get_surface_dr_files(basedir)
        surfacefiles_dt = parse_model_file.get_surface_dt_files(basedir)
        surfacefiles_dte = parse_model_file.get_surface_dte_files(basedir)
        surfacefiles_dre = parse_model_file.get_surface_dre_files(basedir)
        topofzone = parse_model_file.extract_topofzone_names(basedir)
        self.surfacenames = parse_model_file.extract_surface_names(basedir)
        self.surface_attributes = {}
        for i, surfacefile in enumerate(self.surfacefiles):
            self.surface_attributes[get_path(surfacefile)] = {
                "color": get_color(i),
                "order": i,
                "name": self.surfacenames[i],
                "topofzone": topofzone[i],
                "surface": xtgeo.surface_from_file(
                    Path(surfacefile), fformat="irap_binary"
                ),
                "surface_de": xtgeo.surface_from_file(
                    Path(surfacefiles_de[i]), fformat="irap_binary"
                ),
                "surface_dt": xtgeo.surface_from_file(
                    Path(surfacefiles_dt[i]), fformat="irap_binary"
                )
                if surfacefiles_dt is not None
                else None,
                "surface_dr": xtgeo.surface_from_file(
                    Path(surfacefiles_dt[i]), fformat="irap_binary"
                )
                if surfacefiles_dt is not None
                else None,
                "surface_dte": xtgeo.surface_from_file(
                    Path(surfacefiles_dte[i]), fformat="irap_binary"
                )
                if surfacefiles_dte is not None
                else None,
                "surface_dre": xtgeo.surface_from_file(
                    Path(surfacefiles_dre[i]), fformat="irap_binary"
                )
                if surfacefiles_dre is not None
                else None,
            }

        # Log files
        zonation_status_file = parse_model_file.get_zonation_status(basedir)
        well_points_file = parse_model_file.get_well_points(basedir)
        zonelog_name = parse_model_file.get_zonelog_name(basedir)
        self.xsec = HuvXsection(
            self.surface_attributes,
            zonation_status_file,
            well_points_file,
            zonelog_name,
        )
        target_points_file = parse_model_file.get_target_points(basedir)
        self.df_well_target_points = FilterTable(target_points_file, well_points_file)

        # Wellfiles and planned wells
        self.planned_wellfiles = []
        self.planned_wells = {}
        if planned_wells_dir is not None:
            try:
                for file in os.listdir(planned_wells_dir):
                    if Path(file).suffix != ".txt":
                        raise ValueError(
                            f"Planned well file '{file}' is not a txt file \n"
                        )
                self.planned_wellfiles = [
                    os.path.join(planned_wells_dir, file)
                    for file in os.listdir(planned_wells_dir)
                ]
                self.planned_wells = {
                    wf: xtgeo.Well(wf) for wf in self.planned_wellfiles
                }
            # pylint: disable=broad-except
            except Exception as exception:
                self.planned_wells = {}
                self.planned_wellfiles = []
                print("Something went wrong when initializing planned wells.")
                print(type(exception).__name__, ": ", exception)
                print("Fileformat must be type 'ROXAR RMS well'.\n")
        self.wellfiles = parse_model_file.get_well_files(basedir)
        self.wells = {wf: xtgeo.Well(wf) for wf in self.wellfiles}

        # List of wells and surfaces provided
        self.files = []
        self.files += self.wellfiles if self.wellfiles else []
        self.files += self.surfacefiles if self.surfacefiles else []
        self.files += surfacefiles_de if surfacefiles_de else []
        self.files += surfacefiles_dt if surfacefiles_dt else []
        self.files += surfacefiles_dt if surfacefiles_dt else []
        self.files += surfacefiles_dre if surfacefiles_dre else []
        self.files += surfacefiles_dte if surfacefiles_dte else []

        # Store current layers
        self.state = {"switch": False}
        self.layers_state = []

    def ids(self, element):
        return f"{element}-id-{self.uid}"

    @property
    def cross_section_graph_layout(self):
        return html.Div(children=[wcc.Graph(id=self.ids("xsec-view"),)])

    @property
    def cross_section_widgets_layout(self):
        return html.Div(
            children=[
                html.Div(
                    children=[
                        dbc.Button(
                            "Surfaces Settings",
                            id=self.ids("button-open-graph-settings"),
                            color="light",
                            className="mr-1",
                        ),
                        dbc.Modal(
                            children=[
                                dbc.ModalHeader("Surfaces Settings"),
                                dbc.ModalBody(
                                    children=[
                                        html.Label(
                                            style={
                                                "font-weight": "bold",
                                                "textAlign": "Left",
                                            },
                                            children="Select Surfaces",
                                        ),
                                        dcc.Checklist(
                                            id=self.ids("all-surfaces-checkbox"),
                                            options=[{"label": "all", "value": "True"}],
                                            value=["True"],
                                        ),
                                        dcc.Checklist(
                                            id=self.ids("surfaces-checklist"),
                                            options=[
                                                {"label": name, "value": path}
                                                for name, path in zip(
                                                    self.surfacenames, self.surfacefiles
                                                )
                                            ],
                                            value=self.surfacefiles,
                                        ),
                                        dcc.Checklist(
                                            id=self.ids("surfaces-de-checklist"),
                                            options=[
                                                {
                                                    "label": name + "_depth_error",
                                                    "value": path,
                                                    "disabled": False,
                                                }
                                                for name, path in zip(
                                                    self.surfacenames, self.surfacefiles
                                                )
                                            ],
                                            value=self.surfacefiles,
                                        ),
                                    ],
                                ),
                                dbc.ModalFooter(
                                    children=[
                                        dbc.Button(
                                            "Close",
                                            id=self.ids("button-close-graph-settings"),
                                            className="ml-auto",
                                        ),
                                        dbc.Button(
                                            "Apply changes",
                                            id=self.ids("button-apply-checklist"),
                                            className="ml-auto",
                                        ),
                                    ]
                                ),
                            ],
                            id=self.ids("modal-graph-settings"),
                            size="sm",
                            centered=True,
                            backdrop=False,
                            fade=False,
                        ),
                        dbc.Button(
                            "Well Settings", id=self.ids("button-open-well-settings")
                        ),
                        dbc.Modal(
                            children=[
                                dbc.ModalHeader("Well Settings"),
                                dbc.ModalBody(
                                    children=[
                                        html.Label(
                                            style={
                                                "font-weight": "bold",
                                                "textAlign": "Left",
                                            },
                                            children="Select Well Attributes",
                                        ),
                                        dcc.Checklist(
                                            id=self.ids("all-well-settings-checkbox"),
                                            options=[{"label": "all", "value": "True"}],
                                            value=["True"],
                                        ),
                                        dcc.Checklist(
                                            id=self.ids("well-settings-checklist"),
                                            options=[
                                                {
                                                    "label": "Zonelog",
                                                    "value": "zonelog",
                                                },
                                                {
                                                    "label": "Zonation points",
                                                    "value": "zonation_points",
                                                },
                                                {
                                                    "label": "Conditional points",
                                                    "value": "conditional_points",
                                                },
                                            ],
                                            value=[
                                                "zonelog",
                                                "zonation_points",
                                                "conditional_points",
                                            ],
                                        ),
                                    ],
                                ),
                                dbc.ModalFooter(
                                    children=[
                                        dbc.Button(
                                            "Close",
                                            id=self.ids("button-close-well-settings"),
                                            className="ml-auto",
                                        ),
                                        dbc.Button(
                                            "Apply",
                                            id=self.ids(
                                                "button-apply-well-settings-checklist"
                                            ),
                                            className="ml-auto",
                                        ),
                                    ]
                                ),
                            ],
                            id=self.ids("modal-well-settings"),
                            size="sm",
                            centered=True,
                            backdrop=False,
                            fade=False,
                        ),
                    ],
                ),
                wcc.FlexBox(
                    children=[
                        html.Div(
                            children=[
                                html.Label(
                                    style={
                                        "font-weight": "bold",
                                        "textAlign": "center",
                                    },
                                    children="Select well",
                                ),
                                dcc.Dropdown(
                                    id=self.ids("well-dropdown"),
                                    options=[
                                        {"label": self.wells[wf].wellname, "value": wf}
                                        for wf in self.wellfiles
                                    ]
                                    + [
                                        {
                                            "label": self.planned_wells[wf].wellname,
                                            "value": wf,
                                        }
                                        for wf in self.planned_wellfiles
                                    ],
                                    value=self.wellfiles[0],
                                    clearable=False,
                                    disabled=False,
                                ),
                            ]
                        ),
                    ],
                ),
                html.Div(
                    children=[
                        html.Div(
                            style={
                                "marginTop": "0px",
                                "height": "800px",
                                "zIndex": -9999,
                            },
                            children=[self.cross_section_graph_layout],
                            id=self.ids("cross-section-view"),
                        )
                    ]
                ),
            ]
        )

    @property
    def target_points_tab_layout(self):
        df = self.df_well_target_points.get_targetpoints_df()
        return dash_table.DataTable(
            id=self.ids("target-point-table"),
            columns=[{"name": i, "id": i} for i in df.columns],
            data=df.to_dict("records"),
            sort_action="native",
            filter_action="native",
        )

    @property
    def well_points_tab_layout(self):
        return html.Div(
            [
                dbc.Button("Table Settings", id=self.ids("button-open-table-settings")),
                dbc.Modal(
                    children=[
                        dbc.ModalHeader("Table Settings"),
                        dbc.ModalBody(
                            children=[
                                html.Label(
                                    style={"font-weight": "bold", "textAlign": "Left",},
                                    children="Select Table Columns",
                                ),
                                dcc.Checklist(
                                    id=self.ids("columns-checklist"),
                                    options=[
                                        {"label": name, "value": column_name}
                                        for name, column_name in zip(
                                            self.df_well_target_points.get_wellpoints_df()
                                            .keys()
                                            .values,
                                            self.df_well_target_points.get_wellpoints_df()
                                            .keys()
                                            .values,
                                        )
                                    ],
                                    value=[
                                        "Surface",
                                        "Well",
                                        "TVD",
                                        "MD",
                                        "Outlier",
                                        "Deleted",
                                        "Residual",
                                    ],
                                ),
                            ],
                        ),
                        dbc.ModalFooter(
                            children=[
                                dbc.Button(
                                    "Close",
                                    id=self.ids("button-close-table-settings"),
                                    className="ml-auto",
                                ),
                                dbc.Button(
                                    "Apply",
                                    id=self.ids("button-apply-columnlist"),
                                    className="ml-auto",
                                ),
                            ]
                        ),
                    ],
                    id=self.ids("modal-table-settings"),
                    size="sm",
                    centered=True,
                    backdrop=False,
                    fade=False,
                ),
                html.Div(id=self.ids("well-points-table-container")),
            ]
        )

    @property
    def left_flexbox_layout(self):
        return html.Div(
            children=[
                wcc.FlexBox(
                    children=[
                        dcc.RadioItems(
                            labelStyle={"display": "inline-block"},
                            options=[
                                {"label": "Map view", "value": "map-view"},
                                {"label": "Surface picks table", "value": "table-view"},
                            ],
                            id=self.ids("map-table-radioitems"),
                            value="map-view",
                        )
                    ],
                    style={"padding": "5px"},
                ),
                html.Div(
                    id=self.ids("hidden-div-map-view"), children=[self.map_view_layout]
                ),  # Hidden div to store polyline points when in table view
                html.Div(
                    id=self.ids("hidden-div-table-view"),
                    children=[self.table_view_layout],
                ),
            ]
        )

    @property
    def map_view_layout(self):
        return html.Div(
            children=[
                wcc.FlexBox(
                    children=[
                        html.Div(
                            children=[
                                html.Label(
                                    style={
                                        "font-weight": "bold",
                                        "textAlign": "center",
                                    },
                                    children="Select surface",
                                ),
                                dcc.Dropdown(
                                    id=self.ids("map-dropdown"),
                                    options=[
                                        {"label": name, "value": path}
                                        for name, path in zip(
                                            self.surfacenames, self.surfacefiles
                                        )
                                    ],
                                    value=self.surfacefiles[0],
                                    clearable=False,
                                ),
                            ]
                        ),
                    ],
                ),
                html.Div(
                    style={"marginTop": "0px", "height": "800px", "zIndex": -9999,},
                    children=[
                        # pylint: disable=no-member
                        webviz_subsurface_components.NewLayeredMap(
                            id=self.ids("layered-map"),
                            layers=[],
                            unitScale={},
                            autoScaleMap=True,
                            minZoom=-5,
                            drawTools={
                                "drawMarker": False,
                                "drawPolygon": False,
                                "drawPolyline": True,
                                "position": "topright",
                            },
                            switch={
                                "value": self.state["switch"],
                                "disabled": False,
                                "label": "Hillshading",
                            },
                            mouseCoords={"position": "bottomright"},
                            colorBar={"position": "bottomright"},
                        ),
                    ],
                ),
            ]
        )

    @property
    def table_view_layout(self):
        df = self.xsec.get_intersection_dataframe(self.wells[self.wellfiles[0]])
        return html.Div(
            children=[
                html.Label(
                    id=self.ids("surface-picks-label"),
                    style={"font-weight": "bold", "textAlign": "center",},
                ),
                dash_table.DataTable(
                    id=self.ids("uncertainty-table"),
                    columns=[{"name": i, "id": i} for i in df.columns],
                    data=df.to_dict("records"),
                    sort_action="native",
                    filter_action="native",
                ),
            ],
            style={"marginTop": "0px"},
        )

    @property
    def layout(self):
        return dcc.Tabs(
            children=[
                dcc.Tab(
                    label="Cross section & map view",
                    children=[
                        wcc.FlexBox(
                            id=self.ids("layout"),
                            children=[
                                html.Div(
                                    style={"flex": 1}, children=self.left_flexbox_layout
                                ),
                                html.Div(
                                    style={"flex": 1.5},
                                    children=self.cross_section_widgets_layout,
                                ),
                            ],
                        )
                    ],
                ),
                dcc.Tab(
                    label="Target Points",
                    children=[html.Div(children=self.target_points_tab_layout)],
                ),
                dcc.Tab(label="Well Points", children=[self.well_points_tab_layout]),
            ]
        )

    # pylint: disable=too-many-statements
    def set_callbacks(self, app):
        @app.callback(
            Output(self.ids("layered-map"), "layers"),
            [
                Input(self.ids("map-dropdown"), "value"),
                Input(self.ids("layered-map"), "switch"),  # Toggle hillshading on/off
                Input(self.ids("well-dropdown"), "value"),  # Wellfile
            ],
        )
        def _render_map(surfacefile, switch, wellfile):
            """ Renders map view for one surface with de, dt, dte, dr, dre and depth
                Wells marked with circles, trajectory and hillshading toggle
            """
            # Store layers when switching to hillshading
            if self.state["switch"] is not switch["value"]:
                hillshade_layers = self.layers_state.copy()
                for layer in hillshade_layers:
                    if "shader" in layer["data"][0]:
                        layer["data"][0]["shader"]["type"] = (
                            "hillshading" if switch["value"] is True else None
                        )
                        layer["action"] = "update"
                self.state["switch"] = switch["value"]
                return hillshade_layers
            surface_name = self.surface_attributes[get_path(surfacefile)]["name"]
            surfaces = [
                self.surface_attributes[get_path(surfacefile)]["surface"],
                self.surface_attributes[get_path(surfacefile)]["surface_de"],
                self.surface_attributes[get_path(surfacefile)]["surface_dr"],
                self.surface_attributes[get_path(surfacefile)]["surface_dre"],
                self.surface_attributes[get_path(surfacefile)]["surface_dt"],
                self.surface_attributes[get_path(surfacefile)]["surface_dte"],
            ]
            well_layers = get_well_layers(
                self.wells, self.planned_wells, surface_name, surfaces[0], wellfile,
            )
            layers = get_surface_layers(switch, surface_name, surfaces)
            layers.extend(well_layers)
            # Deletes old layers when switching surface in dropdown
            old_layers = self.layers_state
            self.layers_state = layers.copy()
            if old_layers is not None and len(old_layers) > 0:
                for layer in old_layers:
                    layer["action"] = "delete"
                old_layers.extend(layers)
                layers = old_layers
            return layers

        @app.callback(
            Output(self.ids("xsec-view"), "figure"),
            [
                Input(self.ids("button-apply-checklist"), "n_clicks"),
                Input(self.ids("button-apply-well-settings-checklist"), "n_clicks"),
                Input(self.ids("well-dropdown"), "value"),  # wellpath
                Input(self.ids("layered-map"), "polyline_points"),  # Polyline
            ],
            [
                State(self.ids("surfaces-checklist"), "value"),  # surfacefiles
                State(self.ids("surfaces-de-checklist"), "value"),  # surfacefiles keys
                State(self.ids("well-settings-checklist"), "value"),  # Well settings
            ],
        )
        def _render_xsection(
            n_apply_sfc,
            n_apply_well,
            wellfile,
            polyline,
            surfacefiles,
            de_keys,
            well_settings,
        ):
            """ Renders cross section view from wellfile or polyline drawn in map view """
            _ = n_apply_sfc, n_apply_well
            ctx = dash.callback_context
            if wellfile in self.wellfiles:
                well = self.wells[wellfile]
                is_planned = False
            else:
                well = self.planned_wells[wellfile]
                is_planned = True
            well.create_relative_hlen()
            de_keys = [get_path(de_key) for de_key in de_keys]
            surfacefiles = [get_path(sf) for sf in surfacefiles]
            if (
                ctx.triggered[0]["prop_id"]
                == self.ids("layered-map") + ".polyline_points"
                and polyline is not None
            ):
                well = None
            self.xsec.set_de_and_surface_lines(surfacefiles, de_keys, well, polyline)
            self.xsec.set_xsec_fig(
                surfacefiles, de_keys, well_settings, well, is_planned=is_planned
            )
            return self.xsec.fig

        @app.callback(
            Output(self.ids("well-dropdown"), "value"),  # Wellfile
            [Input(self.ids("layered-map"), "clicked_shape")],  # Clicked circle on map
        )
        def _update_render_map_and_xsection(clicked_shape):
            """ Updates well dropdown value when choosing a new circle """
            return (
                clicked_shape["id"] if clicked_shape is not None else self.wellfiles[0]
            )

        @app.callback(
            Output(self.ids("surfaces-checklist"), "value"),
            [Input(self.ids("all-surfaces-checkbox"), "value")],
        )
        def _update_surface_tickboxes(all_surfaces_checkbox):
            """ Toggle on/off all surfaces in graph settings modal """
            return self.surfacefiles if all_surfaces_checkbox == ["True"] else []

        @app.callback(
            Output(self.ids("modal-graph-settings"), "is_open"),
            [
                Input(self.ids("button-open-graph-settings"), "n_clicks"),
                Input(self.ids("button-close-graph-settings"), "n_clicks"),
                Input(self.ids("button-open-graph-settings"), "disabled"),
            ],
            [State(self.ids("modal-graph-settings"), "is_open")],
        )
        def _toggle_modal_graph_settings(n_open, n_close, disabled, is_open):
            """ Open or close graph settings modal button """
            if disabled:
                switch = False
            elif n_open or n_close:
                switch = not is_open
            else:
                switch = is_open
            return switch

        @app.callback(
            Output(self.ids("surfaces-de-checklist"), "options"),
            [Input(self.ids("surfaces-checklist"), "value")],
            [State(self.ids("surfaces-de-checklist"), "options")],
        )
        def _disable_error_checkboxes(surface_values, de_options):
            """ Removes ability to toggle depth error when
            corresponding surface is disabled in graph settings modal
            """
            for i, opt in enumerate(de_options):
                if (surface_values is None) or (opt["value"] not in surface_values):
                    de_options[i]["disabled"] = True
                else:
                    de_options[i]["disabled"] = False
            return de_options

        @app.callback(
            Output(self.ids("well-settings-checklist"), "value"),
            [Input(self.ids("all-well-settings-checkbox"), "value")],
        )
        def _update_well_settings_tickboxes(all_well_attributes_checkbox):
            """ Toggle on/off all options in well settings modal """
            return (
                ["zonelog", "zonation_points", "conditional_points"]
                if all_well_attributes_checkbox == ["True"]
                else []
            )

        @app.callback(
            Output(self.ids("modal-well-settings"), "is_open"),
            [
                Input(self.ids("button-open-well-settings"), "n_clicks"),
                Input(self.ids("button-close-well-settings"), "n_clicks"),
            ],
            [State(self.ids("modal-well-settings"), "is_open")],
        )
        def _toggle_modal_well_settings(n_open, n_close, is_open):
            """ Open or close well settings modal button """
            if n_open or n_close:
                return not is_open
            return is_open

        @app.callback(
            Output(self.ids("well-points-table-container"), "children"),
            [Input(self.ids("button-apply-columnlist"), "n_clicks"),],
            [State(self.ids("columns-checklist"), "value"),],  # columns list
        )
        # pylint: disable=unused-variable, unused-argument
        def display_output(n_clicks, column_list):
            """ Renders wellpoints table from csv file """
            wellpoints_df = self.df_well_target_points.update_wellpoints_df(column_list)
            return html.Div(
                [
                    dash_table.DataTable(
                        id=self.ids("well-points-table"),
                        columns=[{"name": i, "id": i} for i in wellpoints_df.columns],
                        data=wellpoints_df.to_dict("records"),
                        sort_action="native",
                        filter_action="native",
                    ),
                ]
            )

        @app.callback(
            Output(self.ids("modal-table-settings"), "is_open"),
            [
                Input(self.ids("button-open-table-settings"), "n_clicks"),
                Input(self.ids("button-close-table-settings"), "n_clicks"),
            ],
            [State(self.ids("modal-table-settings"), "is_open")],
        )
        def _toggle_modal_table_settings(n_open, n_close, is_open):
            """ Open or close table settings modal button """
            if n_open or n_close:
                return not is_open
            return is_open

        @app.callback(
            [
                Output(self.ids("hidden-div-map-view"), "hidden"),
                Output(self.ids("hidden-div-table-view"), "hidden"),
            ],
            [Input(self.ids("map-table-radioitems"), "value")],
        )
        def _toggle_left_flexbox_content(value):
            """ Returns which left flexbox content is visible/hidden """
            if value == "table-view":
                switch = True, False
            else:
                switch = False, True
            return switch

        @app.callback(
            Output(self.ids("uncertainty-table"), "data"),
            [Input(self.ids("well-dropdown"), "value")],
        )
        def _render_uncertainty_table(wellfile):
            if wellfile in self.wellfiles:
                well = self.wells[wellfile]
            else:
                well = self.planned_wells[wellfile]
            df = self.xsec.get_intersection_dataframe(well)
            return df.to_dict("records")

        @app.callback(
            Output(self.ids("surface-picks-label"), "children"),
            [Input(self.ids("well-dropdown"), "value")],
        )
        def _render_surface_picks_label(wellfile):
            if wellfile in self.wellfiles:
                wellname = self.wells[wellfile].wellname
            else:
                wellname = self.planned_wells[wellfile].wellname
            return f"Surface picks for {wellname}"

    def add_webvizstore(self):
        return [(get_path, [{"path": fn}]) for fn in self.files]


@webvizstore
def get_path(path) -> Path:
    return Path(path)


def get_color(i):
    """ Create a list of colors for surface layers
    Args:
        i: Index of surface layer in surfacefiles list
    Returns:
        List of colors for surface layers
    """
    colors = [
        "rgb(70,130,180)",  # Steel blue
        "rgb(0,0,255)",  # Blue
        "rgb(173,255,47)",  # Green yellow
        "rgb(0,128,0)",  # Green
        "rgb(0,255,0)",  # Lime
        "rgb(60,179,113)",  # Medium sea green
        "rgb(255,105,180)",  # Pink
        "rgb(221,160,221)",  # Plum
        "rgb(255,255,0)",  # Yellow
        "rgb(244,164,96)",  # Tan
        "rgb(255,140,0)",  # Orange
        "rgb(255,69,0)",  # Blood orange
        "rgb(255,0,0)",  # Red
        "rgb(220,20,60)",  # Crimson
        "rgb(255,0,255)",  # Fuchsia
    ]
    n_colors = len(colors)
    return colors[(i) % (n_colors)]

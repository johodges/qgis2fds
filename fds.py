# -*- coding: utf-8 -*-

"""qgis2fds"""

__author__ = "Emanuele Gissi, Ruggero Poletto"
__date__ = "2020-05-04"
__copyright__ = "(C) 2020 by Emanuele Gissi"
__revision__ = "$Format:%H$"  # replaced with git SHA1

from math import sqrt


from qgis.core import QgsExpressionContextUtils, QgsProject
from qgis.utils import pluginMetadata
import time, os
from . import utils, landuse, geometry, wind


def _get_header_comment(landuse_type, wind_filepath):
    plugin_version = pluginMetadata("qgis2fds", "version")
    qgis_version = (
        QgsExpressionContextUtils.globalScope().variable("qgis_version").encode("utf-8")
    )
    qgis_filepath = QgsProject.instance().fileName() or "not saved"
    qgis_filepath_str = qgis_filepath
    if len(qgis_filepath_str) > 60:
        qgis_filepath_str = "..." + qgis_filepath[-57:]
    landuse_type_filepath_str = landuse_type.filepath
    if len(landuse_type_filepath_str) > 60:
        landuse_type_filepath_str = "..." + landuse_type.filepath[-57:]
    wind_filepath_str = wind_filepath or ""
    if len(wind_filepath_str) > 60:
        wind_filepath_str = "..." + wind_filepath[-57:]
    return (
        plugin_version,
        qgis_version,
        qgis_filepath_str,
        landuse_type_filepath_str,
        wind_filepath_str,
    )


def _get_domain(feedback, utm_extent, utm_origin, min_z, max_z, cell_size, nmesh):
    # Calc domain XB, relative to origin
    domain_xb = (
        utm_extent.xMinimum() - utm_origin.x(),
        utm_extent.xMaximum() - utm_origin.x(),
        utm_extent.yMinimum() - utm_origin.y(),
        utm_extent.yMaximum() - utm_origin.y(),
        min_z - 2.0,
        max_z + cell_size * 10,  # 10 cells over max z
    )

    # Calc number of MESH along x and y
    domain_ratio = abs((domain_xb[1] - domain_xb[0]) / (domain_xb[3] - domain_xb[2]))
    nmesh_y = round(sqrt(nmesh / domain_ratio))
    nmesh_x = int(nmesh / nmesh_y)
    feedback.pushInfo(
        f"\nNumber of FDS MESHes: {nmesh_x*nmesh_y} ={nmesh_x:d}x{nmesh_y:d}"
    )

    # Calc MESH XB
    mesh_xb = (
        domain_xb[0],
        domain_xb[0] + (domain_xb[1] - domain_xb[0]) / nmesh_x,
        domain_xb[2],
        domain_xb[2] + (domain_xb[3] - domain_xb[2]) / nmesh_y,
        domain_xb[4],
        domain_xb[5],
    )

    # Calc MESH IJK
    mesh_ijk = (
        int((mesh_xb[1] - mesh_xb[0]) / cell_size),
        int((mesh_xb[3] - mesh_xb[2]) / cell_size),
        int((mesh_xb[5] - mesh_xb[4]) / cell_size),
    )

    # Calc MESH MULT DX DY
    mult_dx, mult_dy = mesh_xb[1] - mesh_xb[0], mesh_xb[3] - mesh_xb[2]

    # Calc MESH size and cell number
    mesh_sizes = (
        round(mesh_xb[1] - mesh_xb[0]),
        round(mesh_xb[3] - mesh_xb[2]),
        round(mesh_xb[5] - mesh_xb[4]),
    )
    ncell = mesh_ijk[0] * mesh_ijk[1] * mesh_ijk[2]
    return nmesh_x, nmesh_y, mesh_xb, mesh_ijk, mult_dx, mult_dy, mesh_sizes, ncell


def _get_terrain_str(
    feedback,
    fds_path,
    chid,
    point_layer,
    utm_origin,
    landuse_layer,
    landuse_type,
    export_obst,
):
    """Get terrain str and export related files, if needed."""
    if export_obst:
        return geometry.get_obst_str(
            feedback=feedback,
            point_layer=point_layer,
            utm_origin=utm_origin,
            landuse_layer=landuse_layer,
            landuse_type=landuse_type,
        )
    else:
        (
            min_z,
            max_z,
        ) = geometry.write_geom_terrain(  # FIXME how to pass both in GEOM and OBSTs?
            feedback=feedback,
            fds_path=fds_path,
            chid=chid,
            point_layer=point_layer,
            utm_origin=utm_origin,
            landuse_layer=landuse_layer,
            landuse_type=landuse_type,
        )
        return f"""&GEOM ID='Terrain'
      SURF_ID={landuse_type.id_str}
      BINARY_FILE='{chid}_terrain.bingeom'
      IS_TERRAIN=T EXTEND_TERRAIN=F /"""


def _get_fds_case_str(
    feedback,
    fds_path,
    dem_layer,
    landuse_layer,
    chid,
    point_layer,
    wgs84_origin,
    utm_origin,
    utm_crs,
    min_z,
    max_z,
    landuse_type,
    utm_extent,
    nmesh,
    cell_size,
    wind_filepath,
    fire_layer,
    export_obst,
):
    # Calc header comment
    (
        plugin_version,
        qgis_version,
        qgis_filepath_str,
        landuse_type_filepath_str,
        wind_filepath_str,
    ) = _get_header_comment(
        landuse_type=landuse_type,
        wind_filepath=wind_filepath,
    )

    # Calc domain
    (
        nmesh_x,
        nmesh_y,
        mesh_xb,
        mesh_ijk,
        mult_dx,
        mult_dy,
        mesh_sizes,
        ncell,
    ) = _get_domain(
        feedback=feedback,
        utm_extent=utm_extent,
        utm_origin=utm_origin,
        min_z=min_z,
        max_z=max_z,
        cell_size=cell_size,
        nmesh=nmesh,
    )

    # Get WIND from file
    wind_ramp_str = wind.get_wind_ramp_str(feedback, wind_filepath)

    # Get terrain OBSTs or GEOM and bingeom
    terrain_str = _get_terrain_str(
        feedback=feedback,
        fds_path=fds_path,
        chid=chid,
        point_layer=point_layer,
        utm_origin=utm_origin,
        landuse_layer=landuse_layer,
        landuse_type=landuse_type,
        export_obst=export_obst,
    )

    # Build string and return it
    return f"""
! Generated by qgis2fds <{plugin_version}> on QGIS <{qgis_version}>
! QGIS file: <{qgis_filepath_str}>
! Date: <{time.strftime("%a, %d %b %Y, %H:%M:%S", time.localtime())}>
! Selected UTM CRS: <{utm_crs.description()}>
! Domain origin: <{utm_origin.x():.1f}, {utm_origin.y():.1f}>
!   {utils.get_lonlat_url(wgs84_origin)}
! Terrain extent: <{utm_extent.toString(precision=1)}>
! DEM layer: <{dem_layer.name()}>
! Landuse layer: <{landuse_layer and landuse_layer.name() or 'None'}>
! Landuse type file: <{landuse_type_filepath_str or 'None'}>
! Fire layer: <{fire_layer and fire_layer.name() or 'None'}>
! Wind file: <{wind_filepath_str or 'None'}>

&HEAD CHID='{chid}' TITLE='Description of {chid}' /

! MISC LEVEL_SET_MODE parameter
! 1: Wind not affected by the terrain. No fire.
! 2: Wind field established over the terrain, then frozen. No fire.
! 3: Wind field following the terrain, no fire.
! 4: Wind and fire fully-coupled.

&MISC ORIGIN_LAT={wgs84_origin.y():.7f} ORIGIN_LON={wgs84_origin.x():.7f} NORTH_BEARING=0.
      TERRAIN_IMAGE='{chid}_tex.png'
      LEVEL_SET_MODE=4 /

&TIME T_END=3600. /

! Example REAC, used when LEVEL_SET_MODE=4
&REAC ID='Wood' SOOT_YIELD=0.02 O=2.5 C=3.4 H=6.2
      HEAT_OF_COMBUSTION=17700 /

! Pressure solver
!PRES VELOCITY_TOLERANCE=1.E-6 MAX_PRESSURE_ITERATIONS=100 /

! Radiation solver
!RADI RADIATION=F /

! Domain and its boundary conditions
! {nmesh_x:d} x {nmesh_y:d} meshes of {mesh_sizes[0]}m x {mesh_sizes[1]}m x {mesh_sizes[2]}m size and {ncell} cells each
&MULT ID='Meshes'
      DX={mult_dx:.3f} I_LOWER=0 I_UPPER={nmesh_x-1:d}
      DY={mult_dy:.3f} J_LOWER=0 J_UPPER={nmesh_y-1:d} /
&MESH IJK={mesh_ijk[0]:d},{mesh_ijk[1]:d},{mesh_ijk[2]:d} MULT_ID='Meshes'
      XB={mesh_xb[0]:.3f},{mesh_xb[1]:.3f},{mesh_xb[2]:.3f},{mesh_xb[3]:.3f},{mesh_xb[4]:.3f},{mesh_xb[5]:.3f} /
&VENT ID='Domain BC XMIN' DB='XMIN' SURF_ID='OPEN' /
&VENT ID='Domain BC XMAX' DB='XMAX' SURF_ID='OPEN' /
&VENT ID='Domain BC YMIN' DB='YMIN' SURF_ID='OPEN' /
&VENT ID='Domain BC YMAX' DB='YMAX' SURF_ID='OPEN' /
&VENT ID='Domain BC ZMAX' DB='ZMAX' SURF_ID='OPEN' /

! Wind
&WIND SPEED=1., RAMP_SPEED='ws', RAMP_DIRECTION='wd' /
{wind_ramp_str}

! Output quantities
&SLCF AGL_SLICE=1. QUANTITY='LEVEL SET VALUE' /
&SLCF AGL_SLICE=2. QUANTITY='VISIBILITY' /
&SLCF AGL_SLICE=2. QUANTITY='TEMPERATURE' VECTOR=T /
&SLCF AGL_SLICE=12. QUANTITY='VISIBILITY' /
&SLCF AGL_SLICE=12. QUANTITY='TEMPERATURE' VECTOR=T /
&SLCF PBX={0.:.3f} QUANTITY='TEMPERATURE' VECTOR=T /
&SLCF PBY={0.:.3f} QUANTITY='TEMPERATURE' VECTOR=T /

! Output for wind rose at origin
&DEVC ID='Origin_UV' XYZ=0.,0.,{(mesh_xb[5]-1.):.3f} QUANTITY='U-VELOCITY' /
&DEVC ID='Origin_VV' XYZ=0.,0.,{(mesh_xb[5]-1.):.3f} QUANTITY='V-VELOCITY' /
&DEVC ID='Origin_WV' XYZ=0.,0.,{(mesh_xb[5]-1.):.3f} QUANTITY='W-VELOCITY' /
 
! Boundary conditions
{landuse_type.surf_str}

! Terrain
{terrain_str}

&TAIL /

"""


def write_case(
    feedback,
    dem_layer,
    landuse_layer,
    fds_path,
    chid,
    wgs84_origin,
    utm_origin,
    utm_crs,
    point_layer,
    landuse_type,
    utm_extent,
    nmesh,
    cell_size,
    wind_filepath,
    fire_layer,
    export_obst,
):

    # Prepare and write bingeom file

    min_z, max_z = 0.0, 200.0  # FIXME FIXME FIXME
    # geometry.write_geom_terrain(
    #    feedback=feedback,
    #    fds_path=fds_path,
    #    chid=chid,
    #    point_layer=point_layer,
    #    utm_origin=utm_origin,
    #    landuse_layer=landuse_layer,
    #    landuse_type=landuse_type,
    # )

    # Prepare and write FDS file

    content = _get_fds_case_str(
        feedback=feedback,
        fds_path=fds_path,
        dem_layer=dem_layer,
        landuse_layer=landuse_layer,
        chid=chid,
        point_layer=point_layer,
        wgs84_origin=wgs84_origin,
        utm_origin=utm_origin,
        utm_crs=utm_crs,
        min_z=min_z,
        max_z=max_z,
        landuse_type=landuse_type,
        utm_extent=utm_extent,
        nmesh=nmesh,
        cell_size=cell_size,
        wind_filepath=wind_filepath,
        fire_layer=fire_layer,
        export_obst=export_obst,
    )
    utils.write_file(
        feedback=feedback,
        filepath=os.path.join(fds_path, f"{chid}.fds"),
        content=content,
    )

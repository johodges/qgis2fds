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

from . import utils


class FDSCase:
    def __init__(
        self,
        feedback,
        fds_path,
        chid,
        domain,
        terrain,
        wind,
    ) -> None:
        self.feedback = feedback
        self.fds_path = fds_path
        self.chid = chid
        self.domain = domain
        self.terrain = terrain
        self.wind = wind

    def get_fds(self):
        # qgis
        plugin_version = pluginMetadata("qgis2fds", "version")
        qgis_version = (
            QgsExpressionContextUtils.globalScope()
            .variable("qgis_version")
            .encode("utf-8")
        )
        qgis_filepath = QgsProject.instance().fileName() or "not saved"
        qgis_filepath_str = (
            len(qgis_filepath) > 60 and "..." + qgis_filepath[-57:] or qgis_filepath
        )
        date = time.strftime("%a, %d %b %Y, %H:%M:%S", time.localtime())
        # Prepare str
        return f"""! Generated by qgis2fds <{plugin_version}> on QGIS <{qgis_version}>
! QGIS file: <{qgis_filepath_str}>
! Date: <{date}>
{self.domain.get_comment()}
{self.terrain.get_comment()}
{self.terrain.landuse_type.get_comment()}
{self.wind.get_comment()}

&HEAD CHID='{self.chid}' TITLE='Description of {self.chid}' /

! MISC LEVEL_SET_MODE parameter
! 1: Wind not affected by the terrain. No fire.
! 2: Wind field established over the terrain, then frozen. No fire.
! 3: Wind field following the terrain, no fire.
! 4: Wind and fire fully-coupled.

&MISC ORIGIN_LAT={self.domain.wgs84_origin.y():.7f}
      ORIGIN_LON={self.domain.wgs84_origin.x():.7f}
      NORTH_BEARING=0.
      TERRAIN_IMAGE='{self.chid}_tex.png'
      LEVEL_SET_MODE=4 /

&TIME T_END=3600. /

! Example REAC, used when LEVEL_SET_MODE=4
&REAC ID='Wood' SOOT_YIELD=0.02 O=2.5 C=3.4 H=6.2
      HEAT_OF_COMBUSTION=17700. /

! Pressure solver
!PRES VELOCITY_TOLERANCE=1.E-6 MAX_PRESSURE_ITERATIONS=100 /

! Radiation solver
!RADI RADIATION=F /
{self.domain.get_fds()}
{self.terrain.landuse_type.get_fds()}

! Output quantities
&SLCF AGL_SLICE=1. QUANTITY='LEVEL SET VALUE' /
&SLCF AGL_SLICE=2. QUANTITY='VISIBILITY' /
&SLCF AGL_SLICE=2. QUANTITY='TEMPERATURE' VECTOR=T /
&SLCF AGL_SLICE=12. QUANTITY='VISIBILITY' /
&SLCF AGL_SLICE=12. QUANTITY='TEMPERATURE' VECTOR=T /
&SLCF PBX={0.:.3f} QUANTITY='TEMPERATURE' VECTOR=T /
&SLCF PBY={0.:.3f} QUANTITY='TEMPERATURE' VECTOR=T /

! Output for wind rose at origin
&DEVC ID='Origin_UV' XYZ=0.,0.,{(self.domain.mesh_xb[5]-1.):.3f} QUANTITY='U-VELOCITY' /
&DEVC ID='Origin_VV' XYZ=0.,0.,{(self.domain.mesh_xb[5]-1.):.3f} QUANTITY='V-VELOCITY' /
&DEVC ID='Origin_WV' XYZ=0.,0.,{(self.domain.mesh_xb[5]-1.):.3f} QUANTITY='W-VELOCITY' /
{self.wind.get_fds()}
{self.terrain.get_fds()}

&TAIL /
"""

    def write(self):
        utils.write_file(
            feedback=self.feedback,
            filepath=os.path.join(self.fds_path, f"{self.chid}.fds"),
            content=self.get_fds(),
        )

# lus_parser_sender.py
# Part of the Line-us extension for Inkscape
# By Yulya & Anatoly Besplemennov (@hihickster @longtolik)
# Version 1.4,  2018-03-24
# This program is based on SVG parser implemented in EggBot Inkscape Extension
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA

from bezmisc import *
from math import sqrt
from simpletransform import *
import gettext
import simplepath
import cspsubdiv
import os

import string
import sys

import socket
import time

N_PEN_DELAY = 0.0    	# delay (seconds) for the pen to go up/down before the next move
N_PAGE_HEIGHT = 2000	# Default page height (each unit equiv. to one step)
N_PAGE_WIDTH = 2000	# Default page width (each unit equiv. to one step)
N_PEN_UP_POS = 1000	# Default pen-up position
N_PEN_DOWN_POS = 0	# Default pen-down position
N_WALK_DEFAULT = 10	# Default steps for walking stepper motors
N_DEFAULT_LAYER = 1	# Default inkscape layer

platform = sys.platform.lower()

HOME = os.getenv( 'HOME' )
USER = os.getenv( 'USER' )
if platform == 'win32':
	HOME = os.path.realpath( "C:/" )  # Arguably, this should be %APPDATA% or %TEMP%

Gcode_file =  os.path.join( HOME,'\\0\\0000007.txt' )
#Gcode_file =  os.path.join( HOME,'\\Users',USER,'\\Documents\\LineUsFiles\\0000007.txt' )

#-----------------------------------------------------------------------------------------------------
def parseLengthWithUnits( str ):
	u = 'px'
	s = str.strip()
	if s[-2:] == 'px':
		s = s[:-2]
	elif s[-1:] == '%':
		u = '%'
		s = s[:-1]

	try:
		v = float( s )
	except:
		return None, None

	return v, u
#-----------------------------------------------------------------------------------------------------
def subdivideCubicPath( sp, flat, i=1 ):

	while True:
		while True:
			if i >= len( sp ):
				return

			p0 = sp[i - 1][1]
			p1 = sp[i - 1][2]
			p2 = sp[i][0]
			p3 = sp[i][1]

			b = ( p0, p1, p2, p3 )

			if cspsubdiv.maxdist( b ) > flat:
				break

			i += 1

		one, two = beziersplitatt( b, 0.5 )
		sp[i - 1][2] = one[1]
		sp[i][0] = two[2]
		p = [one[2], one[3], two[1]]
		sp[i:1] = [p]


#-----------------------------------------------------------------------------------------------------
class LUS( inkex.Effect ):
#-----------------------------------------------------------------------------------------------------
	def __init__( self ):
		inkex.Effect.__init__( self )

		self.OptionParser.add_option( "--smoothness",
			action="store", type="float",
			dest="smoothness", default=0.1,
			help="Smoothness of curves" )

		self.OptionParser.add_option( "--penDelay",
			action="store", type="float",
			dest="penDelay", default=N_PEN_DELAY,
			help="Delay after pen lift/down (sec)" )

		self.OptionParser.add_option( "--tab",
			action="store", type="string",
			dest="tab", default="controls",
			help="The active tab when Apply was pressed" )

		self.OptionParser.add_option( "--penUpPosition",
			action="store", type="int",
			dest="penUpPosition", default=N_PEN_UP_POS,
			help="Position when lifted" )

		self.OptionParser.add_option( "--penDownPosition",
			action="store", type="int",
			dest="penDownPosition", default=N_PEN_DOWN_POS,
			help="Position when lowered" )
		self.OptionParser.add_option( "--layernumber",
			action="store", type="int",
			dest="layernumber", default=N_DEFAULT_LAYER,
			help="Selected layer for multilayer plotting" )
		self.OptionParser.add_option( "--setupType",
			action="store", type="string",
			dest="setupType", default="controls",
			help="The active option when Apply was pressed" )
		self.OptionParser.add_option( "--manualType",
			action="store", type="string",
			dest="manualType", default="controls",
			help="The active option when Apply was pressed" )
		self.OptionParser.add_option( "--WalkDistance",
			action="store", type="int",
			dest="WalkDistance", default=N_WALK_DEFAULT,
			help="Selected layer for multilayer plotting" )

		self.PenIsUp = True
		self.fX = None
		self.fY = None
		self.fPrevX = None
		self.fPrevY = None
		self.ptFirst = None		
		self.nodeCount = int( 0 )
		self.nodeTarget = int( 0 )
		self.pathcount = int( 0 )
		self.LayersPlotted = 0
	
		self.svgLayer = int( 0 )
		self.svgNodeCount = int( 0 )
		self.svgDataRead = False
		self.svgLastPath = int( 0 )
		self.svgLastPathNC = int( 0 )

		self.svgTotalDeltaX = int( 0 )
		self.svgTotalDeltaY = int( 0 )

		nDeltaX = 0
		nDeltaY = 0

		self.svgWidth = float( N_PAGE_WIDTH )
		self.svgHeight = float( N_PAGE_HEIGHT )
		self.svgTransform = [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]
		self.warnings = {}
		self.step_scaling_factor = 1
		self.GF = False  # GF means to Gcode File
		self.LU = False  # LU means to Lune-us
#-----------------------------------------------------------------------------------------------------
	def effect( self ):
		# Main entry

		self.svg = self.document.getroot()
		self.CheckSVGforLUSData()

#____________	Output to Line-us here   ____________________________________

		if self.options.tab == '"splash"':      # Plot
			self.LU = True
			self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
			self.connect()
			self.allLayers = True
			self.plotCurrentLayer = True
			self.svgNodeCount = 0
			self.svgLastPath = 0
			self.svgLayer = 12345;  # indicate that we are plotting all layers.
			self.plotToLUS()

		elif self.options.tab == '"manual"':
			self.LU = True
			self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
			self.connect()
			self.manualCommand()

		elif self.options.tab == '"layers"':
			self.LU = True
			self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
			self.connect()
			self.allLayers = False
			self.plotCurrentLayer = False
			self.LayersPlotted = 0
			self.svgLastPath = 0
			self.svgNodeCount = 0;
			self.svgLayer = self.options.layernumber
			self.plotToLUS()
			if ( self.LayersPlotted == 0 ):
				inkex.errormsg( gettext.gettext( "Did not find any numbered layers to plot." ) )

		#elif self.options.tab == '"setup"':    #just fict op to have smth to close below
			#self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

		#elif self.options.tab == '"options"'':    #just fict op to have smth to close below
			#self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

#____________	Output to G-code file here   ____________________________________

		elif self.options.tab == '"gcode"':    #G-code
			self.GF = True
			self.fil = open(Gcode_file,'w')
			self.fil.write( 'G54 X0 Y0 S1\n' )  # write header needed for Line-us
			self.allLayers = True
			self.plotCurrentLayer = True
			self.svgNodeCount = 0
			self.svgLastPath = 0
			self.svgLayer = 12345;  # indicate that we are plotting all layers.
			self.plotToLUS()

#____________	Common  final section   ____________________________________

		self.svgDataRead = False
		self.UpdateSVGLUSData( self.svg )

		if self.LU: #to Line-us 
			self._sock.close()
		if self.GF:   #to Gcode file
			self.fil.close()

		self.LU= False
		self.GF = False

		return
#-----------------------------------------------------------------------------------------------------
	def CheckSVGforLUSData( self ):
		self.svgDataRead = False
		self.recursiveLUSDataScan( self.svg )
		if ( not self.svgDataRead ):    #if there is no lus data, add some:
			luslayer = inkex.etree.SubElement( self.svg, 'lus' )
		
			luslayer.set( 'layer', str( 0 ) )
			luslayer.set( 'node', str( 0 ) )
			luslayer.set( 'lastpath', str( 0 ) )
			luslayer.set( 'lastpathnc', str( 0 ) )
			luslayer.set( 'totaldeltax', str( 0 ) )
			luslayer.set( 'totaldeltay', str( 0 ) )
#-----------------------------------------------------------------------------------------------------
	def recursiveLUSDataScan( self, aNodeList ):
		if ( not self.svgDataRead ):
			for node in aNodeList:
				if node.tag == 'svg':
					self.recursiveLUSDataScan( node )
				elif node.tag == inkex.addNS( 'botbot', 'svg' ) or node.tag == 'lus':
					
					self.svgLayer = int( node.get( 'layer' ) )
					self.svgNodeCount = int( node.get( 'node' ) )

					try:
						self.svgLastPath = int( node.get( 'lastpath' ) )
						self.svgLastPathNC = int( node.get( 'lastpathnc' ) )
						self.svgTotalDeltaX = int( node.get( 'totaldeltax' ) )
						self.svgTotalDeltaY = int( node.get( 'totaldeltay' ) )
						self.svgDataRead = True
					except:
						node.set( 'lastpath', str( 0 ) )
						node.set( 'lastpathnc', str( 0 ) )
						node.set( 'totaldeltax', str( 0 ) )
						node.set( 'totaldeltay', str( 0 ) )
						self.svgDataRead = True
#-----------------------------------------------------------------------------------------------------
	def UpdateSVGLUSData( self, aNodeList ):
		if ( not self.svgDataRead ):
			for node in aNodeList:
				if node.tag == 'svg':
					self.UpdateSVGLUSData( node )
				elif node.tag == inkex.addNS( 'lus', 'svg' ) or node.tag == 'lus':
					node.set( 'layer', str( self.svgLayer ) )
					node.set( 'node', str( self.svgNodeCount ) )
					node.set( 'lastpath', str( self.svgLastPath ) )
					node.set( 'lastpathnc', str( self.svgLastPathNC ) )
					node.set( 'totaldeltax', str( self.svgTotalDeltaX ) )
					node.set( 'totaldeltay', str( self.svgTotalDeltaY ) )
					self.svgDataRead = True
#-----------------------------------------------------------------------------------------------------
	def manualCommand( self ):

		if self.options.manualType == "none":
			return

		if self.options.manualType == "raise_pen":
			self.penUp()

		elif self.options.manualType == "lower_pen":
			self.penDown()

		elif self.options.manualType == "version_check":
			#strVersion = self.doRequest( chr(0x18))
			strVersion = self.doRequest( )
			inkex.errormsg( 'Version: '+strVersion )

		elif self.options.manualType is "walk_X_motor" or "walk_Y_motor":
			if self.options.manualType == "walk_X_motor":
				nDeltaX = self.options.WalkDistance
				nDeltaY = 0
			elif self.options.manualType == "walk_Y_motor":
				nDeltaY = self.options.WalkDistance
				nDeltaX = 0
			else:
				return

			strOutput = ','.join( ['G01 X'+str( nDeltaX )+' Y'+str( nDeltaY )] )
			self.doCommand( strOutput )

		return
#-----------------------------------------------------------------------------------------------------
	def plotToLUS( self ):
		# Plotting
		#parse the svg data as a series of line segments and send each segment to be plotted

		if ( not self.getDocProps() ):
			# Cannot handle the document's dimensions!!!
			inkex.errormsg( gettext.gettext(
			'The document to be plotted has invalid dimensions. ' +
			'The dimensions must be unitless or have units of pixels (px) or ' +
			'percentages (%). Document dimensions may be set in Inkscape with ' +
			'File > Document Properties' ) )
			return

		# Viewbox handling
		# Also ignores the preserveAspectRatio attribute
		viewbox = self.svg.get( 'viewBox' )
		if viewbox:
			vinfo = viewbox.strip().replace( ',', ' ' ).split( ' ' )
			if ( float(vinfo[2]) != 0 ) and ( float(vinfo[3]) != 0 ):
				sx = self.svgWidth / float( vinfo[2] )
				sy = self.svgHeight / float( vinfo[3] )
				self.svgTransform = parseTransform( 'scale(%f,%f) translate(%f,%f)' % (sx, sy, -float( vinfo[0] ), -float( vinfo[1] ) ) )
		try:
			self.recursivelyTraverseSvg( self.svg, self.svgTransform )
					
			if (  self.ptFirst ):
				self.fX = self.ptFirst[0]
				self.fY = self.ptFirst[1]
				self.nodeCount = self.nodeTarget    # enablesfpx return-to-home only option
				self.plotLine()

				# Return Home here
				self.penUp()
				self.doCommand( 'G01 X1000 Y1000' ) # or G28 Return to Home Position
				#self.doCommand( 'G01 Z1000' ) # or G28 Return to Home Position

				#_______ End of Plotting _______________________________________

			#inkex.errormsg('Final node count: ' + str(self.svgNodeCount)) 			
			self.svgLayer = 0
			#self.svgNodeCount = 0
			self.svgLastPath = 0
			self.svgLastPathNC = 0
			self.svgTotalDeltaX = 0
			self.svgTotalDeltaY = 0
		finally:
			# We may have had an exception
			pass  #inkex.errormsg('End drawing')
#-----------------------------------------------------------------------------------------------------
	def recursivelyTraverseSvg( self, aNodeList,
			matCurrent=[[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]],
			parent_visibility='visible' ):
		for node in aNodeList:
			# Ignore invisible nodes
			v = node.get( 'visibility', parent_visibility )
			if v == 'inherit':
				v = parent_visibility
			if v == 'hidden' or v == 'collapse':
				pass

			# first apply the current matrix transform to this node's tranform
			matNew = composeTransform( matCurrent, parseTransform( node.get( "transform" ) ) )

			if node.tag == inkex.addNS( 'g', 'svg' ) or node.tag == 'g':
				#self.penUp()

				if ( node.get( inkex.addNS( 'groupmode', 'inkscape' ) ) == 'layer' ):
					if not self.allLayers:
						#inkex.errormsg('Plotting layer named: ' + node.get(inkex.addNS('label', 'inkscape')))
						self.DoWePlotLayer( node.get( inkex.addNS( 'label', 'inkscape' ) ) )
				self.recursivelyTraverseSvg( node, matNew, parent_visibility=v )

			elif node.tag == inkex.addNS( 'use', 'svg' ) or node.tag == 'use':

				# A <use> element refers to another SVG element via an xlink:href="#blah"
				# attribute.  We will handle the element by doing an XPath search through
				# the document, looking for the element with the matching id="blah"
				# attribute.  We then recursively process that element after applying
				# any necessary (x,y) translation.
				#
				# Notes:
				#  1. We ignore the height and width attributes as they do not apply to
				#     path-like elements, and
				#  2. Even if the use element has visibility="hidden", SVG still calls
				#     for processing the referenced element.  The referenced element is
				#     hidden only if its visibility is "inherit" or "hidden".

				refid = node.get( inkex.addNS( 'href', 'xlink' ) )
				if refid:
					# [1:] to ignore leading '#' in reference
					path = '//*[@id="%s"]' % refid[1:]
					refnode = node.xpath( path )
					if refnode:
						x = float( node.get( 'x', '0' ) )
						y = float( node.get( 'y', '0' ) )
						# Note: the transform has already been applied
						if ( x != 0 ) or (y != 0 ):
							matNew2 = composeTransform( matNew, parseTransform( 'translate(%f,%f)' % (x,y) ) )
						else:
							matNew2 = matNew
						v = node.get( 'visibility', v )
						self.recursivelyTraverseSvg( refnode, matNew2, parent_visibility=v )
					else:
						pass
				else:
					pass

			elif node.tag == inkex.addNS( 'path', 'svg' ):

				self.pathcount += 1
				self.plotPath( node, matNew )				
				self.svgLastPath += 1
				self.svgLastPathNC = self.nodeCount

			elif node.tag == inkex.addNS( 'rect', 'svg' ) or node.tag == 'rect':

				# Manually transform
				#
				#    <rect x="X" y="Y" width="W" height="H"/>
				#
				# into
				#
				#    <path d="MX,Y lW,0 l0,H l-W,0 z"/>
				#
				# I.e., explicitly draw three sides of the rectangle and the
				# fourth side implicitly

				# Create a path with the outline of the rectangle
				newpath = inkex.etree.Element( inkex.addNS( 'path', 'svg' ) )
				x = float( node.get( 'x' ) )
				y = float( node.get( 'y' ) )
				w = float( node.get( 'width' ) )
				h = float( node.get( 'height' ) )
				s = node.get( 'style' )
				if s:
					newpath.set( 'style', s )
				t = node.get( 'transform' )
				if t:
					newpath.set( 'transform', t )
				a = []
				a.append( ['M ', [x, y]] )
				a.append( [' l ', [w, 0]] )
				a.append( [' l ', [0, h]] )
				a.append( [' l ', [-w, 0]] )
				a.append( [' Z', []] )
				newpath.set( 'd', simplepath.formatPath( a ) )
				self.plotPath( newpath, matNew )

			elif node.tag == inkex.addNS( 'line', 'svg' ) or node.tag == 'line':

				# Convert
				#
				#   <line x1="X1" y1="Y1" x2="X2" y2="Y2/>
				#
				# to
				#
				#   <path d="MX1,Y1 LX2,Y2"/>

				self.pathcount += 1

				# Create a path to contain the line
				newpath = inkex.etree.Element( inkex.addNS( 'path', 'svg' ) )
				x1 = float( node.get( 'x1' ) )
				y1 = float( node.get( 'y1' ) )
				x2 = float( node.get( 'x2' ) )
				y2 = float( node.get( 'y2' ) )
				s = node.get( 'style' )
				if s:
					newpath.set( 'style', s )
				t = node.get( 'transform' )
				if t:
					newpath.set( 'transform', t )
				a = []
				a.append( ['M ', [x1, y1]] )
				a.append( [' L ', [x2, y2]] )
				newpath.set( 'd', simplepath.formatPath( a ) )
				self.plotPath( newpath, matNew )				
				self.svgLastPath += 1
				self.svgLastPathNC = self.nodeCount

			elif node.tag == inkex.addNS( 'polyline', 'svg' ) or node.tag == 'polyline':

				# Convert
				#
				#  <polyline points="x1,y1 x2,y2 x3,y3 [...]"/>
				#
				# to
				#
				#   <path d="Mx1,y1 Lx2,y2 Lx3,y3 [...]"/>
				#
				# Note: we ignore polylines with no points

				pl = node.get( 'points', '' ).strip()
				if pl == '':
					pass

				self.pathcount += 1

				pa = pl.split()
				if not len( pa ):
					pass
				# Issue 29: pre 2.5.? versions of Python do not have
				#    "statement-1 if expression-1 else statement-2"
				# which came out of PEP 308, Conditional Expressions
				#d = "".join( ["M " + pa[i] if i == 0 else " L " + pa[i] for i in range( 0, len( pa ) )] )
				d = "M " + pa[0]
				for i in range( 1, len( pa ) ):
					d += " L " + pa[i]
				newpath = inkex.etree.Element( inkex.addNS( 'path', 'svg' ) )
				newpath.set( 'd', d );
				s = node.get( 'style' )
				if s:
					newpath.set( 'style', s )
				t = node.get( 'transform' )
				if t:
					newpath.set( 'transform', t )
				self.plotPath( newpath, matNew )			
				self.svgLastPath += 1
				self.svgLastPathNC = self.nodeCount

			elif node.tag == inkex.addNS( 'polygon', 'svg' ) or node.tag == 'polygon':

				# Convert
				#
				#  <polygon points="x1,y1 x2,y2 x3,y3 [...]"/>
				#
				# to
				#
				#   <path d="Mx1,y1 Lx2,y2 Lx3,y3 [...] Z"/>
				#
				# Note: we ignore polygons with no points

				pl = node.get( 'points', '' ).strip()
				if pl == '':
					pass

				self.pathcount += 1

				pa = pl.split()
				if not len( pa ):
					pass
				# Issue 29: pre 2.5.? versions of Python do not have
				#    "statement-1 if expression-1 else statement-2"
				# which came out of PEP 308, Conditional Expressions
				#d = "".join( ["M " + pa[i] if i == 0 else " L " + pa[i] for i in range( 0, len( pa ) )] )
				d = "M " + pa[0]
				for i in range( 1, len( pa ) ):
					d += " L " + pa[i]
				d += " Z"
				newpath = inkex.etree.Element( inkex.addNS( 'path', 'svg' ) )
				newpath.set( 'd', d );
				s = node.get( 'style' )
				if s:
					newpath.set( 'style', s )
				t = node.get( 'transform' )
				if t:
					newpath.set( 'transform', t )
				self.plotPath( newpath, matNew )				
				self.svgLastPath += 1
				self.svgLastPathNC = self.nodeCount

			elif node.tag == inkex.addNS( 'ellipse', 'svg' ) or \
				node.tag == 'ellipse' or \
				node.tag == inkex.addNS( 'circle', 'svg' ) or \
				node.tag == 'circle':

					# Convert circles and ellipses to a path with two 180 degree arcs.
					# In general (an ellipse), we convert
					#
					#   <ellipse rx="RX" ry="RY" cx="X" cy="Y"/>
					#
					# to
					#
					#   <path d="MX1,CY A RX,RY 0 1 0 X2,CY A RX,RY 0 1 0 X1,CY"/>
					#
					# where
					#
					#   X1 = CX - RX
					#   X2 = CX + RX
					#
					# Note: ellipses or circles with a radius attribute of value 0 are ignored

					if node.tag == inkex.addNS( 'ellipse', 'svg' ) or node.tag == 'ellipse':
						rx = float( node.get( 'rx', '0' ) )
						ry = float( node.get( 'ry', '0' ) )
					else:
						rx = float( node.get( 'r', '0' ) )
						ry = rx
					if rx == 0 or ry == 0:
						pass

					self.pathcount += 1

					cx = float( node.get( 'cx', '0' ) )
					cy = float( node.get( 'cy', '0' ) )
					x1 = cx - rx
					x2 = cx + rx
					d = 'M %f,%f ' % ( x1, cy ) + \
						'A %f,%f ' % ( rx, ry ) + \
						'0 1 0 %f,%f ' % ( x2, cy ) + \
						'A %f,%f ' % ( rx, ry ) + \
						'0 1 0 %f,%f' % ( x1, cy )
					newpath = inkex.etree.Element( inkex.addNS( 'path', 'svg' ) )
					newpath.set( 'd', d );
					s = node.get( 'style' )
					if s:
						newpath.set( 'style', s )
					t = node.get( 'transform' )
					if t:
						newpath.set( 'transform', t )
					self.plotPath( newpath, matNew )					
					self.svgLastPath += 1
					self.svgLastPathNC = self.nodeCount
			elif node.tag == inkex.addNS( 'metadata', 'svg' ) or node.tag == 'metadata':
				pass
			elif node.tag == inkex.addNS( 'defs', 'svg' ) or node.tag == 'defs':
				pass
			elif node.tag == inkex.addNS( 'namedview', 'sodipodi' ) or node.tag == 'namedview':
				pass
			elif node.tag == inkex.addNS( 'lus', 'svg' ) or node.tag == 'lus':
				pass
			elif node.tag == inkex.addNS( 'title', 'svg' ) or node.tag == 'title':
				pass
			elif node.tag == inkex.addNS( 'desc', 'svg' ) or node.tag == 'desc':
				pass
			elif node.tag == inkex.addNS( 'text', 'svg' ) or node.tag == 'text':
				if not self.warnings.has_key( 'text' ):
					inkex.errormsg( gettext.gettext( 'Warning: unable to draw text; ' +
						'please convert it to a path first.  Consider using the ' +
						'Hershey Text extension which is located under the '+
						'"Render" category of extensions.' ) )
					self.warnings['text'] = 1
				pass
			elif node.tag == inkex.addNS( 'image', 'svg' ) or node.tag == 'image':
				if not self.warnings.has_key( 'image' ):
					inkex.errormsg( gettext.gettext( 'Warning: unable to draw bitmap images; ' +
						'please convert them to line art first.  Consider using the "Trace bitmap..." ' +
						'tool of the "Path" menu.  Mac users please note that some X11 settings may ' +
						'cause cut-and-paste operations to paste in bitmap copies.' ) )
					self.warnings['image'] = 1
				pass
			elif node.tag == inkex.addNS( 'pattern', 'svg' ) or node.tag == 'pattern':
				pass
			elif node.tag == inkex.addNS( 'radialGradient', 'svg' ) or node.tag == 'radialGradient':
				# Similar to pattern
				pass
			elif node.tag == inkex.addNS( 'linearGradient', 'svg' ) or node.tag == 'linearGradient':
				# Similar in pattern
				pass
			elif node.tag == inkex.addNS( 'style', 'svg' ) or node.tag == 'style':
				# This is a reference to an external style sheet and not the value
				# of a style attribute to be inherited by child elements
				pass
			elif node.tag == inkex.addNS( 'cursor', 'svg' ) or node.tag == 'cursor':
				pass
			elif node.tag == inkex.addNS( 'color-profile', 'svg' ) or node.tag == 'color-profile':
				# Gamma curves, color temp, etc. are not relevant to single color output
				pass
			elif not isinstance( node.tag, basestring ):
				# This is likely an XML processing instruction such as an XML
				# comment.  lxml uses a function reference for such node tags
				# and as such the node tag is likely not a printable string.
				# Further, converting it to a printable string likely won't
				# be very useful.
				pass
			else:
				if not self.warnings.has_key( str( node.tag ) ):
					t = str( node.tag ).split( '}' )
					inkex.errormsg( gettext.gettext( 'Warning: unable to draw <' + str( t[-1] ) +
						'> object, please convert it to a path first.' ) )
					self.warnings[str( node.tag )] = 1
				pass
#-----------------------------------------------------------------------------------------------------
	def DoWePlotLayer( self, strLayerName ):

		TempNumString = 'x'
		stringPos = 1
		CurrentLayerName = string.lstrip( strLayerName ) #remove leading whitespace

		# Look at layer name.  Sample first character, then first two, and
		# so on, until the string ends or the string no longer consists of
		# digit characters only.

		MaxLength = len( CurrentLayerName )
		if MaxLength > 0:
			while stringPos <= MaxLength:
				if str.isdigit( CurrentLayerName[:stringPos] ):
					TempNumString = CurrentLayerName[:stringPos] # Store longest numeric string so far
					stringPos = stringPos + 1
				else:
					break

		self.plotCurrentLayer = False    #Temporarily assume that we aren't plotting the layer
		if ( str.isdigit( TempNumString ) ):
			if ( self.svgLayer == int( float( TempNumString ) ) ):
				self.plotCurrentLayer = True	#We get to plot the layer!
				self.LayersPlotted += 1
		#Note: this function is only called if we are NOT plotting all layers.
#-----------------------------------------------------------------------------------------------------
	def getLength( self, name, default ):

		str = self.svg.get( name )
		if str:
			v, u = parseLengthWithUnits( str )
			if not v:
				# Couldn't parse the value
				return None
			elif ( u == '' ) or ( u == 'px' ):
				return v
			elif u == '%':
				return float( default ) * v / 100.0
			else:
				# Unsupported units
				return None
		else:
			# No width specified; assume the default value
			return float( default )
#-----------------------------------------------------------------------------------------------------
	def distance( self, x, y ):
		return sqrt( x * x + y * y )
#-----------------------------------------------------------------------------------------------------
	def getDocProps( self ):

		self.svgHeight = self.getLength( 'height', N_PAGE_HEIGHT )
		self.svgWidth = self.getLength( 'width', N_PAGE_WIDTH )
		if ( self.svgHeight == None ) or ( self.svgWidth == None ):
			return False
		else:
			return True
#-----------------------------------------------------------------------------------------------------
	def plotPath( self, path, matTransform ):

		# turn this path into a cubicsuperpath (list of beziers)...

		d = path.get( 'd' )

		if len( simplepath.parsePath( d ) ) == 0:
			return

		p = cubicsuperpath.parsePath( d )

		# ...and apply the transformation to each point
		applyTransformToPath( matTransform, p )

		# p is now a list of lists of cubic beziers [control pt1, control pt2, endpoint]
		# where the start-point is the last point in the previous segment.
		for sp in p:
			subdivideCubicPath( sp, self.options.smoothness )
			
			nIndex = 0
			for csp in sp:
				self.fX = float( csp[1][0] ) 
				self.fY = float( csp[1][1] )
				# home
				if self.ptFirst is None:				
					self.fPrevX = 0                        #self.svgWidth/2  #( 2 * self.step_scaling_factor )
					self.fPrevY = self.svgHeight   #( 2 * self.step_scaling_factor )
					self.ptFirst = ( self.fPrevX, self.fPrevY )					

				if self.plotCurrentLayer:
					self.plotLine()
					self.fPrevX = self.fX
					self.fPrevY = self.fY
				#self.doCommand(str(nIndex ))
				if self.plotCurrentLayer:
					if nIndex == 0:
						self.penUp()
					elif nIndex == 1:
						self.penDown()			
				nIndex += 1
#-----------------------------------------------------------------------------------------------------
	def penUp( self ):
		if (  not self.PenIsUp  ):			
			self.PenIsUp = True
			if self.LU:
				#self.doCommand( 'G01 Z'+str(self.options.penUpPosition)) # for future needs
				self.doCommand( 'G01 Z1000')  # for a while
				time.sleep(  self.options.penDelay )
#-----------------------------------------------------------------------------------------------------
	def penDown( self ):
		if (   self.PenIsUp  ):
			self.PenIsUp = False
			if self.LU:
				#self.doCommand( 'G01 Z'+str(self.options.penDownPosition)) # for future needs
				self.doCommand( 'G01 Z0')   # for a while
				time.sleep(  self.options.penDelay )
#-----------------------------------------------------------------------------------------------------
	def plotLine( self ):
		if ( self.fPrevX is None ):
			return

		nDeltaX = self.fX - self.fPrevX
		nDeltaY = self.fY - self.fPrevY

		if ( self.distance( nDeltaX, nDeltaY ) > 0 ):
			self.nodeCount += 1

			while ( ( abs( nDeltaX ) > 0 ) or ( abs( nDeltaY ) > 0 ) ):
				xd = nDeltaX
				yd = nDeltaY

				xt = self.svgTotalDeltaX
				yt = -self.svgTotalDeltaY

				if self.LU:	  #to Lineus
					#strOutput = ','.join( ['G01 X'+("%d" % xt)+' Y'+("%d" % yt)])

					if ( xt*yt != 0):   # such a patch
						strOutput = ','.join( ['G01 X'+("%d" % xt)+' Y'+("%d" % yt)])
					else:
						strOutput = ','.join( ['G01 Z1000'] ) # just lift the pen

				if self.GF:  #to Gcode file
					if ( not self.PenIsUp ):
						strOutput = ','.join( ['G01 X'+("%d" % xt)+' Y'+("%d" % yt)+' Z0' ])
					else:
						strOutput = ','.join( ['G01 X'+("%d" % xt)+' Y'+("%d" % yt)+' Z1000'])
						self.doCommand( strOutput )
						strOutput = ','.join( ['G01 X'+("%d" % xt)+' Y'+("%d" % yt)+' Z0'])
				self.doCommand( strOutput )

				self.svgTotalDeltaX += xd
				self.svgTotalDeltaY += yd

				nDeltaX -= xd
				nDeltaY -= yd

#-----------------------------------------------------------------------------------------------------
	def doCommand( self, cmd ):

		if self.LU:  #to Line-us
			cmd += b'\x00'
			response = ''
			try:
				self.send_cmd( cmd )
				while ( response == '' ):
					response =  self.get_resp()
				if ( response[0] != 'o' ):
					inkex.errormsg( cmd )
					inkex.errormsg( str( response ))
					time.sleep( 0.5 )
					self.send_cmd( cmd )  # put it again
					inkex.errormsg('Repeated: '+cmd)
			except:
				pass

		if self.GF:        #to Gcode File
			cmd += '\n'
			try:
				self.send_cmd( cmd )
			except:
				pass
#-----------------------------------------------------------------------------------------------------
	def doRequest( self ):
		if self.connected:
			self._sock.send('Hello')
			line = self.get_resp()
			inkex.errormsg(line)
		return line
#-----------------------------------------------------------------------------------------------------
	def connect( self ):
		try:
			self._sock.connect(('line-us.local',1337))	# Common
			#self._sock.connect(('192.168.43.156', 1337))	# Yulya 
			#self._sock.connect(('10.10.100.254', 1337))	# longtolik
			self.connected=True
		except:
			inkex.errormsg( gettext.gettext( 'Not connected' ) )
			self.connected=False
		return
#-----------------------------------------------------------------------------------------------------
	def get_resp( self ):
		if not self.connected:
			return
		tim=0
		lin = b''
		while ( tim < 1000 ):  # do it 10 seconds
			char = self._sock.recv(1)
			if char != b'\x00':
				lin += char
				tim=0
			elif char == b'\x00':
				break
			tim = tim+1
			time.sleep(0.01)

		if ( tim>990):
			 lin ='Time_out'
		return lin
#-----------------------------------------------------------------------------------------------------
	def send_cmd( self, cmd ):
		if self.LU:  #to Line-us
			if self.connected:
				self._sock.send(cmd)
		if self.GF:  #to Gcode file
			self.fil.write( cmd )
		return
#-----------------------------------------------------------------------------------------------------
#-----------------------------------------------------------------------------------------------------
#-----------------------------------------------------------------------------------------------------


#e = LUS()
#e.affect(output=False)
#e.affect()

# -*- coding: utf-8 -*-
import pygame
import numpy as np

key_to_function = {
    pygame.K_ESCAPE: (lambda x: x.terminate()),         # ESC key to quit
    pygame.K_SPACE:  (lambda x: x.pause())              # SPACE to pause
    }

class VectorViewer:
    """
    Displays 3D vector objects on a Pygame screen.

    @author: kalle
    """

    def __init__(self, width, height):
        self.width = width
        self.height = height
        self.screen = pygame.display.set_mode((width,height))
        self.fullScreen = False
        pygame.display.set_caption('VectorViewer')
        self.backgroundColor = (0,0,0)
        self.VectorObjs = []
        self.midScreen = np.array([width / 2, height / 2], dtype=float)
        self.zScale = width * 0.7                       # Scaling for z coordinates
        self.lightPosition = np.array([400.0, 800.0, -500.0])
        self.target_fps = 60                            # affects movement speeds
        self.running = True
        self.paused = False
        self.clock = pygame.time.Clock()

    def addVectorObj(self, VectorObj):
        self.VectorObjs.append(VectorObj)

    def run(self):
        """ Main loop. """

        while self.running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False
                elif event.type == pygame.KEYDOWN:
                    if event.key in key_to_function:
                        key_to_function[event.key](self)

            if self.paused == True:
                pygame.time.wait(100)

            else:
                # main components executed here
                self.rotate()
                self.display()

                # release any locks on screen
                while self.screen.get_locked():
                    self.screen.unlock()

                # switch between currently showed and the next screen (prepared in "buffer")
                pygame.display.flip()
                self.clock.tick(self.target_fps) # this keeps code running at max target_fps

        # exit; close display, stop music
        pygame.display.quit()

    def rotate(self):
        """
        Rotate all objects. First calculate rotation matrix.
        Then apply the relevant rotation matrix with object position to each VectorObject.
        """

        # rotate and flatten (transform) objects
        for VectorObj in self.VectorObjs:
            VectorObj.increaseAngles()
            VectorObj.setRotationMatrix()
            VectorObj.rotate()
            VectorObj.transform(self.zScale, self.midScreen)

    def display(self):
        """
        Draw the VectorObjs on the screen.
        """

        # lock screen for pixel operations
        self.screen.lock()

        # clear screen.
        self.screen.fill(self.backgroundColor)

        # draw the actual objects
        for VectorObj in self.VectorObjs:
            # first sort object surfaces so that the most distant is first.
            VectorObj.updateSurfaceZPos()
            VectorObj.sortSurfacesByZPos()
            # then draw surface by surface.
            for surface in VectorObj.surfaces:
                # build a list of transNodes for this surface
                node_list = ([VectorObj.transNodes[node][:2] for node in surface.nodes])
                pygame.draw.aalines(self.screen, surface.color, True, node_list)
                pygame.draw.polygon(self.screen, surface.color, node_list, surface.edgeWidth)

        # unlock screen
        self.screen.unlock()

    def terminate(self):

        self.running = False

    def pause(self):

        if self.paused == True:
            self.paused = False
        else:
            self.paused = True

class VectorObject:

    """
    Position is the object's coordinates.
    Nodes are the predefined, static definition of object "corner points", around object position anchor point (0,0,0).
    RotatedNodes are the Nodes rotated by the given Angles and moved to Position.
    TransNodes are the RotatedNodes transformed from 3D to 2D (X.Y) screen coordinates.

    @author: kalle
    """
    def __init__(self):
        self.position = np.array([0.0, 0.0, 0.0, 1.0])      # position
        self.angles = np.array([0.0, 0.0, 0.0])
        self.angleScale = (2.0 * np.pi) / 360.0             # to scale degrees.
        self.rotationMatrix = np.zeros((3,3))
        self.rotateSpeed = np.array([0.0, 0.0, 0.0])
        self.nodes = np.zeros((0, 4))                       # nodes will have unrotated X,Y,Z coordinates plus a column of ones for position handling
        self.rotatedNodes = np.zeros((0, 3))                # rotatedNodes will have X,Y,Z coordinates after rotation ("final 3D coordinates")
        self.transNodes = np.zeros((0, 2))                  # transNodes will have X,Y coordinates
        self.surfaces = []
        self.minShade = 0.2                                 # shade (% of color) to use when surface is parallel to light source

    def setPosition(self, position):
        # move object by giving it a rotated position.
        self.position = position

    def setRotateSpeed(self, angles):
        # set object rotation speed.
        self.rotateSpeed = angles

    def addNodes(self, node_array):
        # add nodes (all at once); add a column of ones for using position in transform
        self.nodes = np.hstack((node_array, np.ones((len(node_array), 1))))
        self.rotatedNodes = node_array # initialize rotatedNodes with nodes (no added ones required)

    def addSurfaces(self, idnum, color, edgeWidth, node_list):
        # add a Surface, defining its properties
        surface = VectorObjectSurface()
        surface.idnum = idnum
        surface.color = color
        surface.edgeWidth = edgeWidth
        surface.nodes = node_list
        self.surfaces.append(surface)

    def increaseAngles(self):
        self.angles += self.rotateSpeed
        for i in range(3):
            if self.angles[i] >= 360: self.angles[i] -= 360
            if self.angles[i] < 0: self.angles[i] += 360

    def setRotationMatrix(self):
        """ Set matrix for rotation using angles. """

        (sx, sy, sz) = np.sin((self.angles) * self.angleScale)
        (cx, cy, cz) = np.cos((self.angles) * self.angleScale)

        # build a matrix for X, Y, Z rotation (in that order, see Wikipedia: Euler angles) including position shift.
        # add a column of zeros for later position use
        self.rotationMatrix = np.array([[cy * cz               , -cy * sz              , sy      ],
                                        [cx * sz + cz * sx * sy, cx * cz - sx * sy * sz, -cy * sx],
                                        [sx * sz - cx * cz * sy, cz * sx + cx * sy * sz, cx * cy ]])

    def updateSurfaceZPos(self):
        # calculate average Z position for each surface using rotatedNodes
        for surface in self.surfaces:
            zpos = sum([self.rotatedNodes[node, 2] for node in surface.nodes]) / len(surface.nodes)
            surface.setZPos(zpos)

    def sortSurfacesByZPos(self):
        # sorts surfaces by Z position so that the most distant comes first in list
        self.surfaces.sort(key=lambda VectorObjectSurface: VectorObjectSurface.zpos, reverse=True)

    def rotate(self):
        """
        Apply a rotation defined by a given rotation matrix.
        """
        matrix = np.vstack((self.rotationMatrix, self.position[0:3]))   # add position to rotation matrix to move object at the same time
        self.rotatedNodes = np.dot(self.nodes, matrix)

    def transform(self, zScale, midScreen):
        """
         Flatten from 3D to 2D and add screen center.
        """
        # apply perspective using Z coordinates and add midScreen to center on screen to get to transNodes.
        # for normal objects, some of the transNodes will not be required, but possibly figuring out which are and processing them
        #   individually could take more time than this.
        self.transNodes = (self.rotatedNodes[:, 0:2] * zScale) / (self.rotatedNodes[:, 2:3]) + midScreen

class VectorObjectSurface:

    """
    Surfaces for a VectorObject.

    @author: kalle
    """
    def __init__(self):
        self.idnum = 0
        # properties set when defining the object
        self.nodes = []
        self.color = (0,0,0)
        self.edgeWidth = 0
        # the following are calculated during program execution
        self.zpos = 0.0

    def setZPos(self, zpos):
        self.zpos = zpos


if __name__ == '__main__':
    """
    Prepare screen, objects etc.
    """

    # set screen size
    # first check available full screen modes
    pygame.display.init()
    # disp_modes = pygame.display.list_modes(0, pygame.FULLSCREEN | pygame.DOUBLEBUF | pygame.HWSURFACE)
    # disp_size = disp_modes[4] # selecting display size from available list. Assuming the 5th element is nice...
    disp_size = (1280, 800)

    vv = VectorViewer(disp_size[0], disp_size[1])

    # set up a simple cube
    vobj = VectorObject()
    # first add nodes, i.e. the corners of the cube, in (X, Y, Z) coordinates
    node_array = np.array([
            [ 100.0, 100.0, 100.0],
            [ 100.0, 100.0,-100.0],
            [ 100.0,-100.0,-100.0],
            [ 100.0,-100.0, 100.0],
            [-100.0, 100.0, 100.0],
            [-100.0, 100.0,-100.0],
            [-100.0,-100.0,-100.0],
            [-100.0,-100.0, 100.0]
            ])
    vobj.addNodes(node_array)
    # then define surfaces
    node_list = [0, 3, 2, 1] # node_list defines the four nodes forming a cube surface, in clockwise order
    vobj.addSurfaces(0, (255,255,255), 0, node_list)
    node_list = [4, 5, 6, 7]
    vobj.addSurfaces(1, (255,255,255), 0, node_list)
    node_list = [0, 1, 5, 4]
    vobj.addSurfaces(2, (150,150,150), 0, node_list)
    node_list = [3, 7, 6, 2]
    vobj.addSurfaces(3, (150,150,150), 0, node_list)
    node_list = [0, 4, 7, 3]
    vobj.addSurfaces(4, (80,80,80), 0, node_list)
    node_list = [1, 2, 6, 5]
    vobj.addSurfaces(5, (80,80,80), 0, node_list)

    speed_angles = np.array([1.0, -.3, 0.55])
    vobj.setRotateSpeed(speed_angles)
    position = np.array([0.0, 0.0, 1500.0, 1.0])
    vobj.setPosition(position)

    # add the object
    vv.addVectorObj(vobj)

    # run the main program
    vv.run()

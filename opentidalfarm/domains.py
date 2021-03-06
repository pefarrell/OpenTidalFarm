from dolfin import *


class RectangularDomain:
    def __init__(self, basin_x, basin_y, nx, ny):
        self.basin_x = basin_x
        self.basin_y = basin_y
        self.nx = nx
        self.ny = ny
        self.mesh = self.generate_mesh(basin_x, basin_y, nx, ny)

        class Left(SubDomain):
            def inside(self, x, on_boundary):
                return on_boundary and near(x[0], 0.0)

        class Right(SubDomain):
            def inside(self, x, on_boundary):
                return on_boundary and near(x[0], basin_x)

        class Sides(SubDomain):
            def inside(self, x, on_boundary):
                return on_boundary and (near(x[1], 0.0) or near(x[1], basin_y))

        # Initialize sub-domain instances
        left = Left()
        right = Right()
        sides = Sides()

        # Initialize mesh function for boundary domains
        self.boundaries = FacetFunction('size_t', self.mesh)
        self.boundaries.set_all(0)
        left.mark(self.boundaries, 1)
        right.mark(self.boundaries, 2)
        sides.mark(self.boundaries, 3)
        self.ds = Measure('ds')[self.boundaries]

    def generate_mesh(self, basin_x, basin_y, nx, ny):
        ''' Generates a rectangular mesh for the divett test
            nx = Number of cells in x direction
            ny = Number of cells in y direction  '''
        # Check if we need to use the new dolfin style classes
        if hasattr(dolfin, "RectangleMesh"):
            mesh = RectangleMesh(0, 0, basin_x, basin_y, nx, ny)
        else:
            mesh = Rectangle(0, 0, basin_x, basin_y, nx, ny)

        mesh.order()
        mesh.init()
        return mesh


class LShapeDomain:
    ''' This class implements the datastructures for a L shaped domain '''

    def __init__(self, filename, length):
        ''' filename must be a valid mesh file that contains a L like geometry. '''

        self.mesh = Mesh(filename)

        # Extract the dimensions
        basin_x = length
        basin_y = length

        class Left(SubDomain):
            def inside(self, x, on_boundary):
                return on_boundary and near(x[0], basin_x)

        class Right(SubDomain):
            def inside(self, x, on_boundary):
                return on_boundary and near(x[1], basin_y)

        class Sides(SubDomain):
            def inside(self, x, on_boundary):
                return on_boundary and not (near(x[1], basin_y) or near(x[0], basin_x))

        # Initialize sub-domain instances
        left = Left()
        right = Right()
        sides = Sides()

        # Initialize mesh function for boundary domains
        self.boundaries = FacetFunction('size_t', self.mesh)
        self.boundaries.set_all(0)
        left.mark(self.boundaries, 1)
        right.mark(self.boundaries, 2)
        sides.mark(self.boundaries, 3)
        self.ds = Measure('ds')[self.boundaries]


class GMeshDomain:
    ''' This class represents a mesh from gmsh '''

    def __init__(self, filename):
        ''' filename must be a valid gmesh file. '''

        self.mesh = Mesh(filename)

        self.boundaries = MeshFunction('size_t', self.mesh, filename[0:-4] + "_facet_region.xml")
        self.ds = Measure('ds')[self.boundaries]

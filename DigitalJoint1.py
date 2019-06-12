#Author-EDM
#Description-Transform an edge on a wood sheet into a tenon + mortise digital joint.

import adsk.core, adsk.fusion, adsk.cam, traceback

# Global list to keep all event handlers in scope.
handlers = []

def run(context):
    ui = None
    try:
        app = adsk.core.Application.get()
        ui  = app.userInterface

        # Get the CommandDefinitions collection.
        cmdDefs = ui.commandDefinitions

        # Create a button command definition.
        button = cmdDefs.addButtonDefinition(
            'DigitalJointCommandID', 'Digital Joint',
            'Select an edge to create a digital joint.'
            )

        # Connect to the command created event.
        commandCreated = CommandCreatedEventHandler()
        button.commandCreated.add(commandCreated)
        handlers.append(commandCreated)

        # Execute the command.
        button.execute()

        # Keep the script running.
        adsk.autoTerminate(False)
    except:
        if ui:
            ui.messageBox('Failed:\n{}'.format(traceback.format_exc()))


# Event handler for the commandCreated event.
class CommandCreatedEventHandler(adsk.core.CommandCreatedEventHandler):
    def __init__(self):
        super().__init__()
    def notify(self, args):
        eventArgs = adsk.core.CommandCreatedEventArgs.cast(args)

        print("In command created event handler!")

        app = adsk.core.Application.get()
        des = adsk.fusion.Design.cast(app.activeProduct)
        cmd = eventArgs.command
        inputs = cmd.commandInputs

        # Command UI
        edgeSelectionInput = inputs.addSelectionInput("edgeSelectionInputID", "Tenon Edge", "Select edge to be transformed")
        edgeSelectionInput.addSelectionFilter("LinearEdges")
        faceSelectionInput = inputs.addSelectionInput("faceSelectionInputID", "Tenon Face", "Select face to be transformed")
        faceSelectionInput.addSelectionFilter("PlanarFaces")
        inputs.addBoolValueInput("isTenonInputID", "Tenon", True, '', True)
        inputs.addBoolValueInput("isMissingStartEdgeID", "Missing Start Side", True, '', False)
        inputs.addBoolValueInput("isMissingEndEdgeID", "Missing End Side", True, '', False)
        inputs.addBoolValueInput("invertDirectionID", "Invert Normal Direction", True, '', False)
        inputs.addIntegerSpinnerCommandInput("numTenonInputID", "Number of tenons", 1, 10, 1, 1)
        inputs.addValueInput("tenonWidthInputID", "Tenon Width", 'mm', adsk.core.ValueInput.createByReal(5))
        inputs.addValueInput("tenonDepthInputID", "Tenon Depth", 'mm', adsk.core.ValueInput.createByReal(1.5))
        inputs.addValueInput("tenonClearanceDepthInputID", "Tenon Clearance Depth", 'mm', adsk.core.ValueInput.createByReal(0))
        inputs.addValueInput("tenonClearanceWidthInputID", "Tenon Clearance Width", 'mm', adsk.core.ValueInput.createByReal(1))
        inputs.addValueInput("tenonPlayID", "Tenon Play Clearance", 'mm', adsk.core.ValueInput.createByReal(0.05))

        # Connect to the execute event.
        onExecute = CommandExecuteHandler()
        cmd.execute.add(onExecute)
        handlers.append(onExecute)

        # Connect to the inputChanged event.
        onExecutePreview = CommandExecutePreviewHandler()
        cmd.executePreview.add(onExecutePreview)
        handlers.append(onExecutePreview)


def print_Point3D(point):
    return "({}, {}, {})".format(point.x, point.y, point.z)
setattr(adsk.core.Point3D, "__str__", print_Point3D)

def print_Vector3D(vector):
    return "({}, {}, {})".format(vector.x, vector.y, vector.z)
setattr(adsk.core.Vector3D, "__str__", print_Vector3D)

def scale_Vector3D(self, other):
    self.scaleBy(other)
    return self
setattr(adsk.core.Vector3D, "__mul__", scale_Vector3D)

def add_Vector3D(self, other):
    self.add(other)
    return self
setattr(adsk.core.Vector3D, "__add__", add_Vector3D)

class SketchBuilder:
    def __init__(self, start_point, x_base_vector, y_base_vector):
        self.current_pos = start_point.copy()
        self.x_base_vector = x_base_vector.copy()
        self.y_base_vector = y_base_vector.copy()

        self.points = []
        self.points.append(start_point.copy())

    def translate_by(self, translation):
        self.current_pos.translateBy(translation)
        self.points.append(self.current_pos.copy())
        return len(self.points) - 1

    def translate(self, x, y):
        self.translate_by(self.x_base_vector.copy() * x + self.y_base_vector.copy() * y)
        return len(self.points) - 1

    def center(self, p1, p2):
        return ((p1.copy().asVector() + p2.copy().asVector()) * 0.5).asPoint()

def filter_profiles(profiles):
    max_area = 0
    max_area_i = 0;
    filtered_profiles = adsk.core.ObjectCollection.create()

    for i in range(profiles.count):
        area = profiles.item(i).areaProperties(adsk.fusion.CalculationAccuracy.HighCalculationAccuracy).area
        if area > max_area:
            max_area_i = i
            max_area = area

    for i in range(profiles.count):
        if i != max_area_i:
            filtered_profiles.add(profiles.item(i))

    return filtered_profiles

class MortiseTenonBuilder:
    def __init__(self):
        pass

    def width(self, value):
        self.width = value
        return self

    def depth(self, value):
        self.depth = value
        return self

    def clearance_width(self, value):
        self.clearance_width = value
        return self

    def clearance_depth(self, value):
        self.clearance_depth = value
        return self

    def play(self, value):
        self.play = value
        return self

    def num_tenons(self, value):
        self.num_tenons = value
        return self

    def is_tenon(self, value):
        self.is_tenon = value
        return self

    def is_missing_start_side(self, value):
        self.is_missing_start_side = value
        return self

    def is_missing_end_side(self, value):
        self.is_missing_end_side = value
        return self

    def invert_normal_dir(self, value):
        self.invert_normal_dir = value
        return self

def build_mortise_tenon(b, edge, face, sketches, extrudes):
    import math

    # Create sketch on input face
    sketch = sketches.add(face)

    edgeLength = edge.length
    if b.is_missing_start_side and b.is_missing_end_side:
        edgeLength += 2 * b.depth
    elif b.is_missing_start_side or b.is_missing_end_side:
        edgeLength += b.depth

    if b.is_tenon:
        b.width = b.width - b.play
        tenon_spacing = (edgeLength - b.num_tenons*b.width)/(b.num_tenons + 1)
    else:
        b.width = b.width - b.play
        tenon_spacing = (edgeLength - b.num_tenons*b.width)/(b.num_tenons + 1) - 2*b.play
        b.width = b.width + 2*b.play
    print("Tenon spacing is {}".format(tenon_spacing))

    if not b.is_tenon:
        (b.width, tenon_spacing) = (tenon_spacing, b.width)

    # Compute sketch edge direction and normal
    startPoint = sketch.modelToSketchSpace(edge.startVertex.geometry.copy())
    endPoint = sketch.modelToSketchSpace(edge.endVertex.geometry.copy())
    edgeDirection = startPoint.vectorTo(endPoint)
    edgeDirection.normalize()
    edgeNormalDirection = edgeDirection.crossProduct(adsk.core.Vector3D.create(0, 0, 1.0 if b.invert_normal_dir else -1.0))
    print("Normal direction is {} (invert_normal_dir = {} / is_tenon = {})".format(edgeNormalDirection, b.invert_normal_dir, b.is_tenon))

    arc_angle = math.pi if b.invert_normal_dir else -math.pi

    # Build edges
    builder = SketchBuilder(startPoint, edgeDirection, edgeNormalDirection) # Point 0 = start point
    if b.is_tenon:
        builder.translate(0, b.depth) # Point 1
        builder.translate(tenon_spacing/2, 0) # Point 2

    for i in range(b.num_tenons):
        if b.is_tenon or i > 0:
            if (b.is_missing_start_side or b.is_missing_end_side) and i == 0:
                if b.is_missing_start_side and b.is_missing_end_side:
                    side_offset = b.depth
                elif b.is_missing_start_side:
                    side_offset = b.depth
                else:
                    side_offset = 0
                builder.translate(tenon_spacing/2 - b.clearance_width - side_offset, 0) # Point 3
            else:
                builder.translate(tenon_spacing/2 - b.clearance_width, 0) # Point 3
            leftArcLeft = builder.translate(0, b.clearance_depth) # Point 4
            leftArcRight = builder.translate(b.clearance_width, 0) # Point 5
            builder.translate(0, -(b.depth + b.clearance_depth)) # Point 6
            builder.translate(b.width, 0) # Point 7
        else:
            builder.translate(b.width + b.play, 0)
        rightArcLeft = builder.translate(0, b.depth + b.clearance_depth) # Point 8
        rightArcRight = builder.translate(b.clearance_width, 0) # Point 9
        builder.translate(0, -b.clearance_depth) # Point 10
        builder.translate(tenon_spacing/2 - b.clearance_width, 0) # Point 10 = Point 2 for next iteration
        if not b.is_tenon and i == b.num_tenons - 1:
            builder.translate(tenon_spacing/2 - b.clearance_width, 0)
            finalArcLeft = builder.translate(0, b.clearance_depth)
            finalArcRight = builder.translate(b.clearance_width, 0)
            builder.translate(0, -(b.depth + b.clearance_depth))

        # Build arcs
        if b.is_tenon or i > 0:
            sketch.sketchCurves.sketchArcs.addByCenterStartSweep(builder.center(builder.points[leftArcLeft], builder.points[leftArcRight]), builder.points[leftArcLeft], arc_angle)
        sketch.sketchCurves.sketchArcs.addByCenterStartSweep(builder.center(builder.points[rightArcLeft], builder.points[rightArcRight]), builder.points[rightArcLeft], arc_angle)
        if not b.is_tenon and i == b.num_tenons - 1:
            sketch.sketchCurves.sketchArcs.addByCenterStartSweep(builder.center(builder.points[finalArcLeft], builder.points[finalArcRight]), builder.points[finalArcLeft], arc_angle)

    builder.translate(tenon_spacing/2, 0)

    points = builder.points
    for i in range(len(points)):
        if i > 0:
            sketch.sketchCurves.sketchLines.addByTwoPoints(points[i-1], points[i])

    # Extrude
    extrudeInput = extrudes.createInput(filter_profiles(sketch.profiles), adsk.fusion.FeatureOperations.CutFeatureOperation)
    extrudeInput.participantBodies = [face.body]
    distance = adsk.core.ValueInput.createByReal(b.depth)
    extrudeInput.setOneSideExtent(adsk.fusion.DistanceExtentDefinition.create(distance), adsk.fusion.ExtentDirections.NegativeExtentDirection)
    extrudes.add(extrudeInput)

# Event handler for the execute event.
class CommandExecuteHandler(adsk.core.CommandEventHandler):
    def __init__(self):
        super().__init__()
    def notify(self, args):
        eventArgs = adsk.core.CommandEventArgs.cast(args)

        # Get sketch currently being edited
        sketches = adsk.core.Application.get().activeProduct.activeComponent.sketches
        extrudes = adsk.core.Application.get().activeProduct.activeComponent.features.extrudeFeatures

        # Find and cast user inputs
        inputs = eventArgs.command.commandInputs

        b = MortiseTenonBuilder()
        b.width(inputs.itemById('tenonWidthInputID').value)
        b.depth(inputs.itemById('tenonDepthInputID').value)
        b.clearance_width(inputs.itemById('tenonClearanceWidthInputID').value)
        b.clearance_depth(inputs.itemById('tenonClearanceDepthInputID').value)
        b.play(inputs.itemById('tenonPlayID').value)
        b.num_tenons(inputs.itemById('numTenonInputID').value)
        b.is_tenon(inputs.itemById('isTenonInputID').value)
        b.is_missing_start_side(inputs.itemById('isMissingStartEdgeID').value)
        b.is_missing_end_side(inputs.itemById('isMissingEndEdgeID').value)
        b.invert_normal_dir(inputs.itemById('invertDirectionID').value)

        faceInput = adsk.core.SelectionCommandInput.cast(inputs.itemById('faceSelectionInputID'))
        face = adsk.fusion.BRepFace.cast(faceInput.selection(0).entity)

        edgeInput = adsk.core.SelectionCommandInput.cast(inputs.itemById('edgeSelectionInputID'))
        edge = adsk.fusion.BRepEdge.cast(edgeInput.selection(0).entity)

        build_mortise_tenon(b, edge, face, sketches, extrudes)

        # Force the termination of the command.
        adsk.terminate()

# Event handler for the executePreview event.
class CommandExecutePreviewHandler(adsk.core.CommandEventHandler):
    def __init__(self):
        super().__init__()
    def notify(self, args):
        eventArgs = adsk.core.CommandEventArgs.cast(args)

# Get sketch currently being edited
        sketches = adsk.core.Application.get().activeProduct.activeComponent.sketches
        extrudes = adsk.core.Application.get().activeProduct.activeComponent.features.extrudeFeatures

        # Find and cast user inputs
        inputs = eventArgs.command.commandInputs

        b = MortiseTenonBuilder()
        b.width(inputs.itemById('tenonWidthInputID').value)
        b.depth(inputs.itemById('tenonDepthInputID').value)
        b.clearance_width(inputs.itemById('tenonClearanceWidthInputID').value)
        b.clearance_depth(inputs.itemById('tenonClearanceDepthInputID').value)
        b.play(inputs.itemById('tenonPlayID').value)
        b.num_tenons(inputs.itemById('numTenonInputID').value)
        b.is_tenon(inputs.itemById('isTenonInputID').value)
        b.is_missing_start_side(inputs.itemById('isMissingStartEdgeID').value)
        b.is_missing_end_side(inputs.itemById('isMissingEndEdgeID').value)
        b.invert_normal_dir(inputs.itemById('invertDirectionID').value)

        faceInput = adsk.core.SelectionCommandInput.cast(inputs.itemById('faceSelectionInputID'))
        face = adsk.fusion.BRepFace.cast(faceInput.selection(0).entity)

        edgeInput = adsk.core.SelectionCommandInput.cast(inputs.itemById('edgeSelectionInputID'))
        edge = adsk.fusion.BRepEdge.cast(edgeInput.selection(0).entity)

        build_mortise_tenon(b, edge, face, sketches, extrudes)


def stop(context):
    try:
        app = adsk.core.Application.get()
        ui  = app.userInterface

        # Delete the command definition.
        cmdDef = ui.commandDefinitions.itemById('DigitalJointCommandID')
        if cmdDef:
            cmdDef.deleteMe()
    except:
        if ui:
            ui.messageBox('Failed:\n{}'.format(traceback.format_exc()))
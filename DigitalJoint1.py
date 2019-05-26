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
        inputs.addBoolValueInput("isMissingEdgesID", "Missing Sides", True, '', False)
        inputs.addIntegerSpinnerCommandInput("numTenonInputID", "Number of tenons", 1, 10, 1, 1)
        inputs.addValueInput("tenonWidthInputID", "Tenon Width", 'mm', adsk.core.ValueInput.createByReal(5))
        inputs.addValueInput("tenonDepthInputID", "Tenon Depth", 'mm', adsk.core.ValueInput.createByReal(1.5))
        inputs.addValueInput("tenonClearanceDepthInputID", "Tenon Clearance Depth", 'mm', adsk.core.ValueInput.createByReal(0))
        inputs.addValueInput("tenonClearanceWidthInputID", "Tenon Clearance Width", 'mm', adsk.core.ValueInput.createByReal(1))
        
        # Connect to the execute event.
        onExecute = CommandExecuteHandler()
        cmd.execute.add(onExecute)
        handlers.append(onExecute)
   

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
    
# Event handler for the execute event.
class CommandExecuteHandler(adsk.core.CommandEventHandler):
    def __init__(self):
        super().__init__()
    def notify(self, args):
        import math
        eventArgs = adsk.core.CommandEventArgs.cast(args)

        # Get sketch currently being edited
        app = adsk.core.Application.get()
        sketches = app.activeProduct.activeComponent.sketches
        extrudes = app.activeProduct.activeComponent.features.extrudeFeatures
        
        # Find and cast user inputs
        inputs = eventArgs.command.commandInputs
        
        # Parameters
        tenon_width = inputs.itemById('tenonWidthInputID').value
        tenon_depth = inputs.itemById('tenonDepthInputID').value
        tenon_height = 1
        tenon_clearance_width = inputs.itemById('tenonClearanceWidthInputID').value 
        tenon_clearance_depth = inputs.itemById('tenonClearanceDepthInputID').value
        num_tenons = inputs.itemById('numTenonInputID').value
        
        isTenon = inputs.itemById('isTenonInputID').value
        isMissingSides = inputs.itemById('isMissingEdgesID').value
        
        faceInput = adsk.core.SelectionCommandInput.cast(inputs.itemById('faceSelectionInputID'))
        face = adsk.fusion.BRepFace.cast(faceInput.selection(0).entity)
        
        # Create sketch on input face
        sketch = sketches.add(face)
        
        edgeInput = adsk.core.SelectionCommandInput.cast(inputs.itemById('edgeSelectionInputID'))
        edge = adsk.fusion.BRepEdge.cast(edgeInput.selection(0).entity)
        edgeLength = edge.length
        if isMissingSides:
            edgeLength += 2 * tenon_depth
        
        tenon_spacing = (edgeLength - num_tenons*tenon_width)/(num_tenons + 1)
        print("Tenon spacing is {}".format(tenon_spacing))

        # Compute sketch edge direction and normal
        startPoint = sketch.modelToSketchSpace(edge.startVertex.geometry.copy())
        endPoint = sketch.modelToSketchSpace(edge.endVertex.geometry.copy())
        edgeDirection = startPoint.vectorTo(endPoint)
        edgeDirection.normalize()
        edgeNormalDirection = edgeDirection.crossProduct(adsk.core.Vector3D.create(0, 0, -1.0))

        # Build edges
        builder = SketchBuilder(startPoint, edgeDirection, edgeNormalDirection) # Point 0 = start point
        if isTenon:
            builder.translate(0, tenon_depth) # Point 1
            builder.translate(tenon_spacing/2, 0) # Point 2
        else:
            (tenon_width, tenon_spacing) = (tenon_spacing, tenon_width)
    
        for i in range(num_tenons):
            if isTenon or i > 0:
                if isMissingSides and i == 0:
                    builder.translate(tenon_spacing/2 - tenon_clearance_width - tenon_depth, 0) # Point 3
                else:
                    builder.translate(tenon_spacing/2 - tenon_clearance_width, 0) # Point 3
                leftArcLeft = builder.translate(0, tenon_clearance_depth) # Point 4
                leftArcRight = builder.translate(tenon_clearance_width, 0) # Point 5
                builder.translate(0, -(tenon_depth + tenon_clearance_depth)) # Point 6
            builder.translate(tenon_width, 0) # Point 7
            rightArcLeft = builder.translate(0, tenon_depth + tenon_clearance_depth) # Point 8
            rightArcRight = builder.translate(tenon_clearance_width, 0) # Point 9
            builder.translate(0, -tenon_clearance_depth) # Point 10
            builder.translate(tenon_spacing/2 - tenon_clearance_width, 0) # Point 10 = Point 2 for next iteration
            if not isTenon and i == num_tenons - 1:
                builder.translate(tenon_spacing/2 - tenon_clearance_width, 0)
                finalArcLeft = builder.translate(0, tenon_clearance_depth)
                finalArcRight = builder.translate(tenon_clearance_width, 0)
                builder.translate(0, -(tenon_depth + tenon_clearance_depth))

            # Build arcs
            if isTenon or i > 0:
                sketch.sketchCurves.sketchArcs.addByCenterStartSweep(builder.center(builder.points[leftArcLeft], builder.points[leftArcRight]), builder.points[leftArcLeft], -math.pi)
            sketch.sketchCurves.sketchArcs.addByCenterStartSweep(builder.center(builder.points[rightArcLeft], builder.points[rightArcRight]), builder.points[rightArcLeft], -math.pi)
            if not isTenon and i == num_tenons - 1:
                sketch.sketchCurves.sketchArcs.addByCenterStartSweep(builder.center(builder.points[finalArcLeft], builder.points[finalArcRight]), builder.points[finalArcLeft], -math.pi)
    
        builder.translate(tenon_spacing/2, 0)

        points = builder.points
        for i in range(len(points)):
            if i > 0:
                sketch.sketchCurves.sketchLines.addByTwoPoints(points[i-1], points[i])
        
        # Extrude
        extrudeInput = extrudes.createInput(filter_profiles(sketch.profiles), adsk.fusion.FeatureOperations.CutFeatureOperation)
        extrudeInput.participantBodies = [face.body]
        distance = adsk.core.ValueInput.createByReal(tenon_depth)
        extrudeInput.setOneSideExtent(adsk.fusion.DistanceExtentDefinition.create(distance), adsk.fusion.ExtentDirections.NegativeExtentDirection)
        extrudes.add(extrudeInput)

        # Force the termination of the command.
        adsk.terminate()   
        

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
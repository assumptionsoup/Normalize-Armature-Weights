''' Normalize weights on armature vertex groups while holding the current 
group.  Assumes there is only one armature on the object.'''
'''
*******************************************************************************
	License and Copyright
	Copyright 2012 Jordan Hueckstaedt
	This program is free software: you can redistribute it and/or modify
	it under the terms of the GNU General Public License as published by
	the Free Software Foundation, either version 3 of the License, or
	(at your option) any later version.

	This program is distributed in the hope that it will be useful,
	but WITHOUT ANY WARRANTY; without even the implied warranty of
	MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
	GNU General Public License for more details.

	You should have received a copy of the GNU General Public License
    along with this program.  If not, see <http://www.gnu.org/licenses/>.
'''

bl_info = {
	'name': 'Normalize Armature Weights',
	'author': 'Jordan Hueckstaedt',
	'version': (1, 0),
	'blender': (2, 63, 0),
	'location': 'View > Weight Tools > Normalize Armature',
	'warning': '', # used for warning icon and text in addons panel
	'description': 'Uses Normalize All on groups attached to armature bones.',
	"wiki_url": "",
	"tracker_url": "",
	"support": 'TESTING',
	'category': 'Paint'
}
import bpy
import bmesh

def restore_mode(mode):
	''' Restores current mode assuming that the passed mode was obtained from
	bpy.context.mode'''
	
	if 'EDIT' in mode:
		mode = 'EDIT'
	elif "_" in mode:
		mode = mode.split("_")
		mode = "%s_%s" % (mode[-1], mode[0])
	bpy.ops.object.mode_set(mode = mode, toggle = False)
	
def assign_all_groups(context, group_indexes):
	'''Ensure that all vertices are assigned to the given group indexes
	
	This was written because I didn't see any other way to assign a weight to
	a vertex that was not already in a group.'''
	
	obj = context.object
	
	# Save state
	mode = context.mode
	old_weight = context.scene.tool_settings.vertex_group_weight
	
	# Set state
	bpy.ops.object.mode_set(mode = 'EDIT', toggle = False)
	active_index = obj.vertex_groups.active_index
	context.scene.tool_settings.vertex_group_weight = 0.0
	
	# Find vertices not in groups
	not_found = [[] for i in group_indexes]
	for vert in obj.data.vertices:
		for x, index in enumerate(group_indexes):
			if not any(index == group_info.group for group_info in vert.groups):
				not_found[x].append(vert.index)
	
	# Select vertices not in groups and add them (at 0 weight)
	mesh = bmesh.from_edit_mesh(obj.data)
	for x in range(len(group_indexes)):
		bpy.ops.mesh.select_all(action = 'DESELECT')
		
		for vert in not_found[x]:
			mesh.verts[vert].select = 1
		
		obj.vertex_groups.active_index = group_indexes[x]
		bpy.ops.object.vertex_group_assign()
	
	# Restore previous state
	restore_mode(mode)
	context.scene.tool_settings.vertex_group_weight = old_weight
	obj.vertex_groups.active_index = active_index
	mesh.free()
	obj.data.update()
	
def normalize_armature( cls, context ):
	# Currently assume only one armature.  I don't really want
	# to deal with multiple ones right now.
	obj = context.object
	mesh = obj.data
	
	# Find armature group.
	bones = []
	armatures = 0
	for mod in obj.modifiers:
		if mod.type == 'ARMATURE' and mod.use_vertex_groups and mod.object:
				bones = [bone.name for bone in mod.object.data.bones]
				armatures += 1
				if armatures == 2:
					break
	
	# Error checking.
	if not bones:
		cls.report({'ERROR'}, "No armature found on object.")
		return {'CANCELLED'}
	
	if obj.vertex_groups.active.name not in bones:
		cls.report({'ERROR'}, "Current vertex group not found on armature.")
		return {'CANCELLED'}

	if armatures > 1:
		cls.report({'WARNING'}, "Multiple armatures found on object.  Operator may have unexpected results.")
	
	# Get bone indexes
	bone_indexes = [group.index for group in obj.vertex_groups if group.name in bones]
	assign_all_groups(context, bone_indexes)
	bone_indexes = set(bone_indexes)
	
	active_index = obj.vertex_groups.active_index
	for vert in obj.data.vertices:
		# Gather weight data of vertex.
		# Also clamp individual weights between 0 and 1.
		groups = vert.groups
		active_group = -1
		weights = []
		indexes = []
		sum = 0
		sum_other = 0
		for x, group in enumerate(groups):
			if group.group in bone_indexes:
				group.weight = max(min(group.weight, 1.0), 0.0)
				weights.append( group.weight )
				indexes.append( x )
				sum += group.weight
				if group.group != active_index:
					sum_other += group.weight
				else:
					active_group = x
					
		# Apply normalization
		if sum != 1.0:
			# This will actually almost always get triggered due to rounding
			# errors.  If anyone knows a stable way to get around this, please
			# let me know.  Rounding might work, but I'd rather not round away
			# real errors either.
			if active_group == -1 and sum_other:
				# Vertex not in active group.  Normalize proportionally.
				for x, weight in enumerate(weights):
					groups[indexes[x]].weight = weight / sum_other
			else:
				if weights[indexes.index(active_group)] >= 1.0:
					# Active group is at or above 1.  Make other weights zero.
					for x, weight in enumerate(weights):
						groups[indexes[x]].weight = 0.0
					groups[active_group].weight = 1.0
				else:
					bias = 1.0 - groups[active_group].weight
					if sum_other:
						# Other groups have some weights.  Distribute remaining proportionally among them.
						# This also may have issues from rounding errors (choosing to dump nearly
						# .999 onto a vert because it was at 0.001 and the other was at 0.0001)
						for x, weight in enumerate(weights):
							if indexes[x] != active_group:
								groups[indexes[x]].weight = bias * ( weight / sum_other )
					elif sum and len(weights) > 1:
						# Active group has weight, which is not 1, and other groups have no weight.  
						# Distribute the remaining proportionally.
						weight = bias * (1 / len(weights))
						for x in range(len(weights)):
							if indexes[x] != active_group:
								groups[indexes[x]].weight = weight
		
	obj.data.update()
	return {'FINISHED'}

class NormalizeArmatureWeights(bpy.types.Operator):
	bl_idname = "object.weightpaint_normalize_armature_weights"
	bl_label = "Normalize Armature Weights"
	bl_options = {'REGISTER', 'UNDO'}
	
	active_index = None
	
	@classmethod
	def poll(cls, context):
		obj = context.active_object
		return (obj and obj.mode == 'WEIGHT_PAINT' and obj.type == 'MESH' and len(obj.vertex_groups) > 0)
	
	def execute(self, context):
		result = normalize_armature( self, context )
		
		# This is a hack.  For some reason the active vertex group changes during execution,
		if self.active_index is not None:
			context.active_object.vertex_groups.active_index = self.active_index
		
		# context.user_preferences.edit.use_global_undo = global_undo_state
		return result
	
	def invoke(self, context, event):
		self.active_index = context.active_object.vertex_groups.active_index
		return self.execute(context)

def panel_func(self, context):	
	row = self.layout.row(align = True)
	row.operator("object.weightpaint_normalize_armature_weights", text="Normalize Armature")

def register():
	bpy.utils.register_module(__name__)
	bpy.types.VIEW3D_PT_tools_weightpaint.append(panel_func)
	
def unregister():
	bpy.utils.unregister_module(__name__)
	bpy.types.VIEW3D_PT_tools_weightpaint.remove(panel_func)
	
if __name__ == "__main__":
	register()
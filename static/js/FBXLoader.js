/**
 * @author Don McCurdy / https://www.donmccurdy.com
 * @source https://github.com/donmccurdy/three.js
 * @license MIT
 */

THREE.FBXLoader = ( function () {

	'use strict';

	function FBXLoader( manager ) {

		this.manager = ( manager !== undefined ) ? manager : THREE.DefaultLoadingManager;

	}

	FBXLoader.prototype = {

		constructor: FBXLoader,

		load: function ( url, onLoad, onProgress, onError ) {

			var scope = this;

			this.resourcePath = THREE.Loader.prototype.extractUrlBase( url );

			new THREE.FileLoader( this.manager )
				.setPath( this.resourcePath )
				.setResponseType( 'arraybuffer' )
				.load( url, function ( text ) {

					try {

						onLoad( scope.parse( text.buffer ) );

					} catch ( e ) {

						if ( onError ) {

							onError( e );

						} else {

							console.error( e );
							scope.manager.itemError( url );

						}

					}

				}, onProgress, onError );

		},

		parse: function ( buffer ) {

			var FBXTree = new FBXTreeParser();
			if ( ! FBXTree.parse( buffer ) ) {

						console.warn( 'THREE.FBXLoader: FBXTree has no content.' );
						return this;

			}

			var connections = new FBXConnections();
			var geometryParser = new GeometryParser();
			var textureParser = new TextureParser( this.manager );

			var fbxObjects = new FBXObjects( FBXTree, connections, geometryParser, textureParser );

			var sceneGraph = new SceneGraph( fbxObjects, connections );

			var materials = [];
			var textureMaps = {};
			var modelScenes = [];

			var modelNodes = fbxObjects.Objects.Model;

			for ( var modelID in modelNodes ) {

				var modelNode = modelNodes[ modelID ];
				var model = new THREE.Group();
				model.name = THREE.PropertyBinding.sanitizeNodeName( modelNode.attrName );

				var children = connections.get( modelID ).children;

				for ( var i = 0; i < children.length; ++ i ) {

					var childID = children[ i ];
					var childNode = fbxObjects.Objects.Model[ childID ];

					if ( childNode !== undefined ) {

						var child = sceneGraph.generateSceneGraph( childNode, model, childID, textureMaps );
						model.add( child );

					}

				}

				modelScenes.push( model );

			}

			return sceneGraph.decompress( modelScenes );

		}

	};

	/**
	 * Parses FBXTree and returns a representation of the FBX scene
	 * @constructor
	 */
	function FBXTreeParser() {

	}

	FBXTreeParser.prototype = {

		constructor: FBXTreeParser,

		// getNodesFromProperty: function ( property, parentID, parentID2, parentID3 ) {
		// },

		parse: function ( buffer ) {

			if ( isFbxFormatBinary( buffer ) ) {

				this.parseBinary( buffer );

			} else {

				var text = new TextDecoder().decode( buffer );
				this.parseASCII( text );

			}

		},

		parseBinary: function ( buffer ) {

			var reader = new DataView( buffer );
			var end = buffer.byteLength;

			this.root = this.parseNode( reader, 0, end, 0 );

		},

		parseASCII: function ( text ) {

			var lines = text.split( '\n' );
			var currentIndent = 0;
			var indent = 0;
			var parents = [];
			var scope = this;

			function parseNode( line ) {

				var tokens = line.split( '"' ).map( function ( token ) { return token.trim(); } );
				var nodeName = tokens[ 0 ];
				var attributes = {};

				for ( var i = 1; i < tokens.length; i += 2 ) {

					var attributeName = tokens[ i ];
					var attributeValue = tokens[ i + 1 ].replace( /,/g, '' );
					attributes[ attributeName ] = attributeValue;

				}

				var node = {
					name: nodeName,
					attributes: attributes,
					children: []
				};

				if ( currentIndent > indent ) {

					parents.push( scope );
					scope = scope.children[ scope.children.length - 1 ];

				} else if ( currentIndent < indent ) {

					parents.pop();
					scope = parents[ parents.length - 1 ];

				}

				indent = currentIndent;
				currentIndent += 1;

				scope.children.push( node );
				return node;

			}

			var root = { name: 'Root', attributes: {}, children: [] };
			parents.push( root );
			scope = root;

			for ( var i = 0; i < lines.length; i ++ ) {

				var line = lines[ i ];
				if ( line.length === 0 ) continue;
				if ( line[ 0 ] === ';' ) continue;
				if ( line[ 0 ] === '\t' ) line = line.substring( 1 );
				parseNode( line );

			}

			this.root = root.children[ 0 ];

		},

		parseNode: function ( reader, start, end, parentID ) {

			var node = {};
			var name = this.parseString( reader, start, end );
			var id = this.parseUInt32( reader, start + 8 );
			var type = this.parseUInt32( reader, start + 12 );
			var size = this.parseUInt32( reader, start + 16 );

			start += 20;

			if ( type === 0 ) {

				// Node
				var attributes = {};
				var numProperties = this.parseUInt32( reader, start );
				start += 4;

				for ( var i = 0; i < numProperties; i ++ ) {

					var propertyName = this.parseString( reader, start, end );
					var propertyType = this.parseString( reader, start, end );
					start += propertyName.length + 1;
					start += propertyType.length + 1;

					switch ( propertyType ) {

						case 'S':
							var value = this.parseString( reader, start, end );
							start += value.length + 1;
							attributes[ propertyName ] = value;
							break;

						case 'F':
							var value = this.parseFloat32( reader, start );
							start += 4;
							attributes[ propertyName ] = value;
							break;

						case 'I':
							var value = this.parseInt32( reader, start );
							start += 4;
							attributes[ propertyName ] = value;
							break;

						case 'Y':
							var value = this.parseBoolean( reader, start );
							start += 1;
							attributes[ propertyName ] = value;
							break;

						case 'C':
							var value = this.parseString( reader, start, end );
							start += value.length + 1;
							attributes[ propertyName ] = value;
							break;

						case 'D':
							var value = this.parseDouble( reader, start );
							start += 8;
							attributes[ propertyName ] = value;
							break;

						case 'b':
						case 'f':
						case 'd':
						case 'i':
						case 'l':
							var arrayLength = this.parseUInt32( reader, start );
							start += 4;
							var encoding = this.parseString( reader, start, end );
							start += encoding.length + 1;
							var arrayType = this.parseString( reader, start, end );
							start += arrayType.length + 1;
							var byteSize = this.parseUInt32( reader, start );
							start += 4;
							var values = [];

							switch ( arrayType ) {

								case 'b':
								for ( var j = 0; j < arrayLength; j ++ ) {
									values.push( this.parseBoolean( reader, start ) );
									start += 1;
								}
								break;

								case 'i':
									for ( var j = 0; j < arrayLength; j ++ ) {
										values.push( this.parseInt32( reader, start ) );
										start += 4;
									}
									break;

								case 'f':
									for ( var j = 0; j < arrayLength; j ++ ) {
										values.push( this.parseFloat32( reader, start ) );
										start += 4;
									}
									break;

								case 'd':
									for ( var j = 0; j < arrayLength; j ++ ) {
										values.push( this.parseDouble( reader, start ) );
										start += 8;
									}
									break;

								case 'l':
									for ( var j = 0; j < arrayLength; j ++ ) {
										values.push( this.parseString( reader, start, end ) );
										start += values[ values.length - 1 ].length + 1;
									}
									break;

							}

							attributes[ propertyName ] = values;
							break;

						default:
							console.warn( 'THREE.FBXLoader: Unknown property type', propertyType );
							break;

					}

				}

				node = {
					name: name,
					id: id,
					type: type,
					size: size,
					attributes: attributes,
					parentID: parentID
				};

			} else if ( type === 1 ) {

				// Property
				node = {
					name: name,
					id: id,
					type: type,
					size: size,
					parentID: parentID
				};

			} else if ( type === 2 ) {

				// Data
				node = {
					name: name,
					id: id,
					type: type,
					size: size,
					parentID: parentID,
					data: new Uint8Array( buffer, start, start + size )
				};

			}

			return node;

		},

		parseString: function ( reader, start, end ) {

			var length = this.parseUInt32( reader, start );
			var string = new TextDecoder().decode( new Uint8Array( reader.buffer, start + 4, start + 4 + length ) );
			return string;

		},

		parseUInt32: function ( reader, start ) {

			return reader.getUint32( start, true );

		},

		parseInt32: function ( reader, start ) {

			return reader.getInt32( start, true );

		},

		parseFloat32: function ( reader, start ) {

			return reader.getFloat32( start, true );

		},

		parseDouble: function ( reader, start ) {

			return reader.getFloat64( start, true );

		},

		parseBoolean: function ( reader, start ) {

			return reader.getUint8( start ) === 1;

		}

	};

	/**
	 * Serves as the base for FBX objects and collections.
	 * @constructor
	 */
	function FBXObjects( FBXTree, connections, geometryParser, textureParser ) {

		this.FBXTree = FBXTree;
		this.connections = connections;
		this.geometryParser = geometryParser;
		this.textureParser = textureParser;

		this.Objects = {};

	}

	FBXObjects.prototype = {

		constructor: FBXObjects,

		getObject: function ( id ) {

			return this.Objects[ id ];

		},

		parseObjects: function () {

			var objects = this.FBXTree.root.Objects;

			for ( var id in objects ) {

				var object = objects[ id ];
				var name = object.attrName;

				switch ( object.attrType ) {

					case 'Geometry':
						this.Objects[ id ] = this.parseGeometry( id, object );
						break;

					case 'Material':
						this.Objects[ id ] = this.parseMaterial( id, object );
						break;

					case 'Texture':
						this.Objects[ id ] = this.parseTexture( id, object );
						break;

					case 'Model':
						this.Objects[ id ] = this.parseModel( id, object );
						break;

					case 'NodeAttribute':
						this.Objects[ id ] = this.parseNodeAttribute( id, object );
						break;

					case 'AnimationStack':
						this.Objects[ id ] = this.parseAnimationStack( id, object );
						break;

					case 'AnimationLayer':
						this.Objects[ id ] = this.parseAnimationLayer( id, object );
						break;

					case 'AnimationCurve':
						this.Objects[ id ] = this.parseAnimationCurve( id, object );
						break;

					case 'AnimationCurveNode':
						this.Objects[ id ] = this.parseAnimationCurveNode( id, object );
						break;

					case 'Deformer':
						this.Objects[ id ] = this.parseDeformer( id, object );
						break;

					default:
						console.warn( 'THREE.FBXLoader: Unknown object type:', object.attrType );
						break;

				}

			}

		},

		parseModel: function ( id, object ) {

			var model = {
				id: id,
				name: object.attrName,
				type: object.attrType,
				connections: [],
				children: [],
				parents: []
			};

			return model;

		},

		parseNodeAttribute: function ( id, object ) {

			var nodeAttribute = {
				id: id,
				name: object.attrName,
				type: object.attrType,
				connections: [],
				children: [],
				parents: []
			};

			return nodeAttribute;

		},

		parseAnimationStack: function ( id, object ) {

			var animationStack = {
				id: id,
				name: object.attrName,
				type: object.attrType,
				connections: [],
				children: [],
				parents: []
			};

			return animationStack;

		},

		parseAnimationLayer: function ( id, object ) {

			var animationLayer = {
				id: id,
				name: object.attrName,
				type: object.attrType,
				connections: [],
				children: [],
				parents: []
			};

			return animationLayer;

		},

		parseAnimationCurve: function ( id, object ) {

			var animationCurve = {
				id: id,
				name: object.attrName,
				type: object.attrType,
				connections: [],
				children: [],
				parents: []
			};

			return animationCurve;

		},

		parseAnimationCurveNode: function ( id, object ) {

			var animationCurveNode = {
				id: id,
				name: object.attrName,
				type: object.attrType,
				connections: [],
				children: [],
				parents: []
			};

			return animationCurveNode;

		},

		parseDeformer: function ( id, object ) {

			var deformer = {
				id: id,
				name: object.attrName,
				type: object.attrType,
				connections: [],
				children: [],
				parents: []
			};

			return deformer;

		},

		parseGeometry: function ( id, object ) {

			var geometry = this.geometryParser.parse( id, object );
			geometry.id = id;
			geometry.name = object.attrName;
			geometry.type = object.attrType;
			geometry.connections = [];
			geometry.children = [];
			geometry.parents = [];

			return geometry;

		},

		parseMaterial: function ( id, object ) {

			var material = {
				id: id,
				name: object.attrName,
				type: object.attrType,
				connections: [],
				children: [],
				parents: []
			};

			return material;

		},

		parseTexture: function ( id, object ) {

			var texture = this.textureParser.parse( id, object );
			texture.id = id;
			texture.name = object.attrName;
			texture.type = object.attrType;
			texture.connections = [];
			texture.children = [];
			texture.parents = [];

			return texture;

		}

	};

	/**
	 * Manages the connections between FBX objects.
	 * @constructor
	 */
	function FBXConnections() {

		this.connections = {};

	}

	FBXConnections.prototype = {

		constructor: FBXConnections,

		add: function ( id, parentID, childID ) {

			if ( this.connections[ id ] === undefined ) {

				this.connections[ id ] = {
					parents: [],
					children: []
				};

			}

			this.connections[ id ].parents.push( parentID );
			this.connections[ id ].children.push( childID );

		},

		get: function ( id ) {

			return this.connections[ id ];

		},

		getParents: function ( id ) {

			return this.connections[ id ] ? this.connections[ id ].parents : undefined;

		},

		getChildren: function ( id ) {

			return this.connections[ id ] ? this.connections[ id ].children : undefined;

		}

	};

	/**
	 * Parses geometry data from FBXTree and returns THREE.BufferGeometry
	 * @constructor
	 */
	function GeometryParser() {

	}

	GeometryParser.prototype = {

		constructor: GeometryParser,

		parse: function ( id, object ) {

			var geometry = new THREE.BufferGeometry();

			var vertices = object.vertices;
			var normals = object.normals;
			var uvs = object.uvs;
			var indices = object.indices;

			// Set vertices
			if ( vertices !== undefined && vertices.length > 0 ) {

				geometry.setAttribute( 'position', new THREE.Float32BufferAttribute( vertices, 3 ) );

			}

			// Set normals
			if ( normals !== undefined && normals.length > 0 ) {

				geometry.setAttribute( 'normal', new THREE.Float32BufferAttribute( normals, 3 ) );

			}

			// Set uvs
			if ( uvs !== undefined && uvs.length > 0 ) {

				geometry.setAttribute( 'uv', new THREE.Float32BufferAttribute( uvs, 2 ) );

			}

			// Set indices
			if ( indices !== undefined && indices.length > 0 ) {

				geometry.setIndex( indices );

			}

			return geometry;

		}

	};

	/**
	 * Parses texture data from FBXTree and returns THREE.Texture
	 * @constructor
	 */
	function TextureParser( manager ) {

		this.manager = manager;

	}

	TextureParser.prototype = {

		constructor: TextureParser,

		parse: function ( id, object ) {

			var texture = new THREE.Texture();

			texture.name = object.attrName;
			texture.url = object.url;

			texture.needsUpdate = true;

			this.manager.itemStart( id );

			var loader = new THREE.ImageLoader( this.manager );
			loader.setPath( this.manager.getPath( object.url ) );
			loader.load( object.url, function ( image ) {

				texture.image = image;
				texture.needsUpdate = false;
				texture.emit( 'loaded' );

			} );

			return texture;

		}

	};

	/**
	 * Generates scene graph from FBX objects and connections
	 * @constructor
	 */
	function SceneGraph( fbxObjects, connections ) {

		this.fbxObjects = fbxObjects;
		this.connections = connections;

	}

	SceneGraph.prototype = {

		constructor: SceneGraph,

		generateSceneGraph: function ( node, parent, id, textureMaps ) {

			var object = this.fbxObjects.getObject( id );

			if ( object === undefined ) {

				return;

			}

			var mesh = this.generateMesh( object, textureMaps );
			if ( mesh !== undefined ) {

				parent.add( mesh );
				return mesh;

			}

			var group = new THREE.Group();
			group.name = object.name;
			parent.add( group );

			return group;

		},

		generateMesh: function ( object, textureMaps ) {

			if ( object.type === 'Geometry' ) {

				var geometry = object;
				var material = new THREE.MeshBasicMaterial();

				// Apply texture if available
				if ( textureMaps !== undefined && textureMaps[ object.id ] !== undefined ) {

					material.map = textureMaps[ object.id ];

				}

				var mesh = new THREE.Mesh( geometry, material );
				mesh.name = object.name;

				return mesh;

			}

		},

		decompress: function ( modelScenes ) {

			return modelScenes;

		}

	};

	/**
	 * Checks if the FBX file is binary
	 * @param {ArrayBuffer} buffer - the file data
	 * @returns {boolean} - true if binary, false if ASCII
	 */
	function isFbxFormatBinary( buffer ) {

		var header = new Uint8Array( buffer, 0, 23 );
		return ( header[ 0 ] === 0x4B && header[ 1 ] === 0x58 );

	}

	return FBXLoader;

} )();

## MODIFIED Requirements

### Requirement: A peer that has ended can be garbage collected

The peer SHALL NOT keep itself alive once it has ended. When the caller no longer references a peer that has ended, the garbage collector SHALL be able to free it together with its reader, its writer and its attached endpoint.

#### Scenario: Peer is stopped

- **WHEN** a started peer is stopped
- **AND** the caller no longer references it
- **THEN** the peer is freed by a garbage collection once the event loop has finished its current step

#### Scenario: Remote side closes the connection

- **WHEN** the remote side closes the connection of a started peer
- **AND** the peer's completion has resolved
- **AND** the caller no longer references the peer
- **THEN** the peer is freed by the next garbage collection

#### Scenario: Peer with an attached endpoint

- **WHEN** an endpoint is attached to a started peer
- **AND** the peer has answered a request with one of the endpoint's handlers
- **AND** the connection has closed and the caller references neither the peer nor the endpoint
- **THEN** the peer and the endpoint are freed by the next garbage collection

#### Scenario: Peer that was called through a definition

- **WHEN** a caller has called a method through `remote` of a started peer
- **AND** the connection has closed and the caller references neither the peer nor the object from `remote`
- **THEN** the peer is freed by the next garbage collection

## ADDED Requirements

### Requirement: A definition states the methods of an interface once

A definition SHALL be a subclass of `JsonRpcEndpoint`, which the `jsonrpcpeer` package exports, whose methods carry the mark `rpc_request` or `rpc_notification` with the name of the method on the wire. Each such method SHALL take one parameter, the params. Its annotations state the type of the params and, for a request, the type of the result.

#### Scenario: A method that a subclass leaves out

- **WHEN** a method of a definition is also marked `abstractmethod`
- **AND** a subclass does not override it
- **THEN** creating an object of the subclass raises a `TypeError` that names the method

#### Scenario: All methods are implemented

- **WHEN** a subclass overrides every abstract method of a definition
- **THEN** an object of the subclass can be created

#### Scenario: A method with a default implementation

- **WHEN** a marked method of a definition has a body and is not marked `abstractmethod`
- **AND** a subclass does not override it
- **THEN** an object of the subclass can be created
- **AND** when that object is attached to a peer, the method of the definition answers

### Requirement: An attached endpoint answers the methods of its definition

`attach_endpoint` SHALL register every marked method of the class of an endpoint, also a method that overrides a marked method of a base class without a mark of its own. The name on the wire SHALL come from the nearest mark in the class hierarchy. The peer SHALL call the method that the object has, and convert the params to the annotation of that method, as for every other handler.

#### Scenario: A request

- **WHEN** an object of a class that implements a definition is attached to a peer
- **AND** a request with the name from the definition arrives
- **THEN** the override is called with the params converted to the annotation of the override
- **AND** the request is answered with what the override returns

#### Scenario: A notification

- **WHEN** an object of a class that implements a definition is attached to a peer
- **AND** a notification with the name from the definition arrives
- **THEN** the override is called with the params converted to the annotation of the override

#### Scenario: The endpoint knows its peer

- **WHEN** an endpoint is attached to a peer
- **THEN** its `rpc_peer` is that peer

#### Scenario: An override without an annotation

- **WHEN** an override has no annotation for its parameter
- **AND** a request with the name from the definition arrives
- **THEN** the override is called with the params as they arrived

#### Scenario: A further subclass overrides it again

- **WHEN** a class derives from an implementation of a definition and overrides a method again
- **AND** an object of that class is attached to a peer
- **THEN** a request with the name from the definition calls the override of that class

#### Scenario: An override with a mark of its own

- **WHEN** an override carries a mark with another name
- **AND** an object of that class is attached to a peer
- **THEN** a request with the name of the override's mark calls it
- **AND** a request with the name from the definition is answered with `-32601`

#### Scenario: A marked method without a separate definition

- **WHEN** a subclass of `JsonRpcEndpoint` has a marked method with a body and is the only class that names it
- **AND** an object of that class is attached to a peer
- **THEN** a request with the name of the mark calls the method

### Requirement: Calling a method of a definition sends it to the other side

`remote` of a peer SHALL return, for a definition, an object of that definition whose marked methods send to the other side of the connection. A request method SHALL wait for the response and return its result converted to the return annotation. A notification method SHALL send and return `None` without waiting for anything.

#### Scenario: A request

- **WHEN** a caller calls a request method through `remote` with params
- **THEN** the peer sends a request with the name from the definition and these params
- **AND** the call returns the result converted to the return annotation

#### Scenario: The params as a keyword

- **WHEN** a caller passes the params by the name of the parameter in the definition
- **THEN** the peer sends the same message as for a positional argument

#### Scenario: A request method without a return annotation

- **WHEN** a request method of a definition has no return annotation
- **AND** a caller calls it through `remote`
- **THEN** the call returns the result as it arrived

#### Scenario: A notification

- **WHEN** a caller calls a notification method through `remote` with params
- **THEN** the peer sends a notification with the name from the definition and these params, without an `id`
- **AND** the call returns `None`

#### Scenario: The other side answers with an error

- **WHEN** a caller calls a request method through `remote`
- **AND** the other side answers with an error
- **THEN** the call raises a `JsonRpcResponseError` with the code, message and data of that error

#### Scenario: The connection is closed

- **WHEN** the connection of a peer has closed
- **AND** a caller calls a request method through `remote`
- **THEN** the call raises a connection-closed error

#### Scenario: The result does not fit the annotation

- **WHEN** a caller calls a request method through `remote`
- **AND** the result cannot be converted to the return annotation
- **THEN** the call raises the error of the conversion
- **AND** the connection stays open

#### Scenario: The object is of the definition

- **WHEN** a caller gets an object from `remote` for a definition
- **THEN** the object is an instance of that definition

#### Scenario: A method with a default implementation

- **WHEN** a marked method of a definition has a body and is not marked `abstractmethod`
- **AND** a caller calls it through `remote`
- **THEN** the peer sends it to the other side, and the body does not run

### Requirement: `remote` refuses what is not a definition

`remote` SHALL raise a `TypeError` when it gets something that is not a subclass of `JsonRpcEndpoint`, or a definition with a marked method that does not take exactly one parameter. The message SHALL name what it refuses.

#### Scenario: A class that is not an endpoint

- **WHEN** a caller passes a class that does not derive from `JsonRpcEndpoint` to `remote`
- **THEN** `remote` raises a `TypeError` that names the class

#### Scenario: A method with two parameters

- **WHEN** a marked method of a definition takes two parameters besides `self`
- **AND** a caller passes that definition to `remote`
- **THEN** `remote` raises a `TypeError` that names the method

### Requirement: Type checkers see the definition at the call

For a type checker such as `mypy` or `pyright`, the result of `remote` SHALL be an object of the definition it gets, also when the definition is abstract, and the calling project SHALL NOT need a setting of its own for that.

#### Scenario: An abstract definition

- **WHEN** a caller passes an abstract definition to `remote`
- **THEN** the type checker reports no error, and the type of the result is the definition

#### Scenario: Params of the wrong type

- **WHEN** a caller calls a method through `remote` with params of another type than the definition states
- **THEN** the type checker reports an error

#### Scenario: A method that the definition does not have

- **WHEN** a caller calls a method through `remote` that the definition does not have
- **THEN** the type checker reports an error

#### Scenario: The type of the result

- **WHEN** a caller awaits a request method through `remote`
- **THEN** the type of the result is the return annotation of the definition

### Requirement: An endpoint calls the other side of its peer

`remote` of an endpoint SHALL do the same as `remote` of the peer that it is attached to. If the endpoint has no peer, it SHALL raise a `RuntimeError` that names the class of the endpoint.

#### Scenario: An attached endpoint

- **WHEN** an attached endpoint calls a method through its `remote`
- **THEN** its peer sends it to the other side

#### Scenario: An endpoint without a peer

- **WHEN** an endpoint that was never attached, or whose `rpc_peer` was set to `None`, calls its `remote`
- **THEN** `remote` raises a `RuntimeError` that names the class of the endpoint

### Requirement: Several endpoints share one peer

A peer SHALL answer the methods of every endpoint attached to it, and SHALL call any definition through `remote`. The definition SHALL select the interface. Two handlers for the same name on the wire SHALL raise `JsonRpcMethodAlreadyRegisteredError`, and the message SHALL name the method.

#### Scenario: Two endpoints on one peer

- **WHEN** objects of two classes that implement different definitions are attached to one peer
- **THEN** each of them answers the methods of its definition

#### Scenario: One class implements two definitions

- **WHEN** one class derives from two definitions and implements both
- **AND** an object of that class is attached to a peer
- **THEN** it answers the methods of both

#### Scenario: Two handlers for one method

- **WHEN** two endpoints with a method of the same name on the wire are attached to one peer
- **THEN** attaching the second raises `JsonRpcMethodAlreadyRegisteredError`

#### Scenario: Two definitions with a method of the same Python name

- **WHEN** two definitions each have a method `log`, with different names on the wire
- **AND** a caller calls `log` through `remote` for each of them
- **THEN** each call sends the name from its own definition

#### Scenario: Both directions on one connection

- **WHEN** one side implements a definition and calls another, and the other side does the opposite
- **THEN** the calls of both sides get their responses on the one connection

#### Scenario: A definition that the peer also implements

- **WHEN** an object that implements a definition is attached to a peer
- **AND** a caller calls a method of that definition through `remote` of that peer
- **THEN** the call goes to the other side, and the attached object is not called

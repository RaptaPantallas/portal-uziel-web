"use strict";

var QWebChannelMessageTypes = {
    Init: 0,
    Idle: 1,
    NewMetaData: 2,
    NewData: 3,
    Signal: 4,
    Response: 5,
    PropertyUpdate: 6,
    DetailUpdate: 7,
    ObjectPropertyUpdate: 8,
    ObjectPropertyResponse: 9
};

var QWebChannel = function(transport, initCallback) {
    if (typeof transport !== "object" || typeof transport.send !== "function") {
        console.error("The QWebChannel requires a transport object. Passed: " + typeof transport);
        return;
    }

    var channel = this;
    this.transport = transport;

    this.execCallbacks = {};
    this.execId = 0;
    this.objects = {};

    this.send = function(data) {
        if (typeof data !== "string") {
            data = JSON.stringify(data);
        }
        channel.transport.send(data);
    };

    this.transport.onmessage = function(message) {
        var m = message.data;
        if (typeof m === "string") {
            m = JSON.parse(m);
        }
        switch (m.type) {
            case QWebChannelMessageTypes.Signal:
                channel.handleSignal(m);
                break;
            case QWebChannelMessageTypes.Response:
                channel.handleResponse(m);
                break;
            case QWebChannelMessageTypes.PropertyUpdate:
            case QWebChannelMessageTypes.ObjectPropertyUpdate:
                channel.handlePropertyUpdate(m);
                break;
            default:
                console.error("invalid message received: ", m);
                break;
        }
    };

    this.exec = function(data, callback) {
        if (callback) {
            var id = channel.execId++;
            channel.execCallbacks[id] = callback;
            data.id = id;
        }
        channel.send(data);
    };

    this.handleSignal = function(message) {
        var object = channel.objects[message.object];
        if (object) {
            object.signalEmitted(message.signal, message.args);
        } else {
            console.warn("Unhandled signal: " + message.object + "::" + message.signal);
        }
    };

    this.handleResponse = function(message) {
        if (!message.hasOwnProperty("id")) {
            console.error("Invalid response message received: ", JSON.stringify(message));
            return;
        }
        channel.execCallbacks[message.id](message.data);
        delete channel.execCallbacks[message.id];
    };

    this.handlePropertyUpdate = function(message) {
        for (var i in message.signals) {
            var detail = message.signals[i];
            this.handleSignal(detail);
        }
        for (var objectName in message.properties) {
            var object = channel.objects[objectName];
            if (object) {
                object.propertyUpdate(message.properties[objectName]);
            }
        }
    };

    var initQObject = function(name, data, channel) {
        var properties = data.properties || [];
        var signals = data.signals || [];
        var methods = data.methods || [];
        var object = {};

        object.objectName = name;
        object.propertyUpdate = function(props) {
            for (var name in props) {
                object[name] = props[name];
            }
        };

        object.signalEmitted = function(signalName, args) {
            var signal = object[signalName];
            if (signal && signal.connections) {
                for (var i = 0; i < signal.connections.length; ++i) {
                    signal.connections[i].apply(null, args);
                }
            }
        };

        var setupProperty = function(propName) {
            Object.defineProperty(object, propName, {
                get: function() { return object["_" + propName]; },
                set: function(value) {
                    if (value === object["_" + propName]) return;
                    object["_" + propName] = value;
                    channel.exec({
                        type: QWebChannelMessageTypes.ObjectPropertyUpdate,
                        object: name,
                        property: propName,
                        value: value
                    });
                }
            });
        };

        for (var i = 0; i < properties.length; ++i) {
            var prop = properties[i];
            object["_" + prop[0]] = prop[1];
            setupProperty(prop[0]);
        }

        var setupSignal = function(signalName) {
            var signal = {
                connections: [],
                connect: function(callback) {
                    if (typeof callback !== "function") {
                        console.error("Only functions can be connected to signals.");
                        return;
                    }
                    signal.connections.push(callback);
                },
                disconnect: function(callback) {
                    var index = signal.connections.indexOf(callback);
                    if (index !== -1) {
                        signal.connections.splice(index, 1);
                    }
                }
            };
            object[signalName] = signal;
        };

        for (var i = 0; i < signals.length; ++i) {
            setupSignal(signals[i]);
        }

        var setupMethod = function(methodName) {
            object[methodName] = function() {
                var args = [];
                var callback;
                for (var i = 0; i < arguments.length; ++i) {
                    if (typeof arguments[i] === "function") {
                        callback = arguments[i];
                        break;
                    }
                    args.push(arguments[i]);
                }
                channel.exec({
                    type: QWebChannelMessageTypes.Response,
                    object: name,
                    method: methodName,
                    args: args
                }, callback);
            };
        };

        for (var i = 0; i < methods.length; ++i) {
            setupMethod(methods[i]);
        }

        channel.objects[name] = object;
    };

    channel.exec({type: QWebChannelMessageTypes.Init}, function(data) {
        for (var name in data) {
            initQObject(name, data[name], channel);
        }
        if (initCallback) {
            initCallback(channel);
        }
    });
};

if (typeof module === "object") {
    module.exports = {
        QWebChannel: QWebChannel
    };
}

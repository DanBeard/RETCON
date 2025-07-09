var http = require('http'),
    httpProxy = require('http-proxy'),
    fs = require('fs');

const homedir = require('os').homedir();
const args = process.argv
const bindIp = args[2]


if(bindIp) { 
    console.log("Binding to " + bindIp);
    httpProxy.createServer({
    target: {
        host: bindIp,
        port: 8000
    },
    ssl: {
        key: fs.readFileSync(homedir+'/.retcon/key.pem', 'utf8'),
        cert: fs.readFileSync(homedir+'/.retcon/cert.pem', 'utf8')
    }
    }).listen(8443, bindIp);

    httpProxy.createServer({
    target: {
        host: bindIp,
        port: 80
    },
    ssl: {
        key: fs.readFileSync(homedir+'/.retcon/key.pem', 'utf8'),
        cert: fs.readFileSync(homedir+'/.retcon/cert.pem', 'utf8')
    }
    }).listen(443, bindIp);
} else {
    console.log("Exiting, no bind ip set")
}
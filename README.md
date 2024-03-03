# FDFTP-rdt_on_udp
A simple version of reliable data transmission implemented on UDP, including the sender-end and receiver-end

## 使用说明
### 1. 在config.py中修改启动设置，各参数说明如下:<br>
>* DEBUG: 调试所用，会输出更多的调试时所用信息（大量IO操作会影响性能）
>* START_INTERVAL: 握手操作的超时检测的起始时间间隔，每次超时加倍
>* MINMIN_CONGESTION_CONTROL_FILE_SZ: 最小开启拥塞状态转换的文件大小(小文件可以直接一直慢启动使拥塞控制窗口加倍，不进入拥塞避免状态的淹没方式得到较高的gootput（虽然有较高的丢包，但速度快了很多，不需要经历慢启动）)
>* MAX_TRY_COUNTS: 最大尝试次数，注意成功接收后interval会回到START_INTERVAL
>* BUF_SIZE: 套接字的缓存大小，设置越大越好
>* SERVER_IP: 服务端的IP地址
>* SERVER_PORT： 服务端的端口，如果服务端不知道哪些端口可用， 可设置为0自动分配，服务端启动后会输出一次端口号，客户端一定要设置确切的端口号
>* MSS: 最大报文段长度，**请勿修改**
>* MAX_HEADER_SZ：所使用的协议的头部的最大长度， **请勿修改**
>* SEG_SZ: 将文件分为若干个SEG_SZ字节的segments，数据包中所含文件的最小单元，**请勿修改**

**应该需要修改的就只有SERVER_IP和SERVER_PORT**<br>
### 2. 先启动服务端，启动服务端之后根据服务端显示的端口号，将客户端的config.py中的SERVER_PORT修改为实际绑定的值
### 3. 在客户端命令行进行操作，使用upload file或者download file来上传或下载文件
### 4. 服务端的退出命令是quit，会等待与客户端的任务完成之后再真正退出
### 5. 客户端的退出命令是#quit，在传输时不可用
#### NOTE
* 有时候“卡死”是正常的，可能是网络状况不好一直在进行接收尝试，有耐心可以多等一会儿或者直接退出重启，也可以把MAX_TRY_COUNTS设置得小一点
* 有时候可能会看似“无法退出”，这是因为在挥手过程中网络波动，没有收到相应的信号，会超时后重新等待，如果TASK输出了信息，可以直接ctrl+c退出
* 上传完成之后最好等待一段时间再进行下载，否则可能会因为上次的连接，服务端还在等待挥手信号而卡死
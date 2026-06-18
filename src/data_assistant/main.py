from src.data_assistant.logger import logger

"""数据助手 - 入口模块"""
def main():
    logger.info("数据助手启动中....")
    logger.debug(f"当前工作目录：...")
    logger.info("数据助手启动完成")

if __name__ == "__main__":
	main()

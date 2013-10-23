-- phpMyAdmin SQL Dump
-- version 3.3.7deb7
-- http://www.phpmyadmin.net
--
-- Host: localhost
-- Generation Time: Oct 23, 2013 at 02:31 PM
-- Server version: 5.1.72
-- PHP Version: 5.3.3-7+squeeze17

SET SQL_MODE="NO_AUTO_VALUE_ON_ZERO";


/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!40101 SET NAMES utf8 */;

--
-- Database: `ti`
--

-- --------------------------------------------------------

--
-- Table structure for table `keyphrase`
--

CREATE TABLE IF NOT EXISTS `keyphrase` (
  `id` bigint(20) unsigned NOT NULL AUTO_INCREMENT,
  `method` int(11) NOT NULL,
  `text` text NOT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8 AUTO_INCREMENT=1 ;

-- --------------------------------------------------------

--
-- Table structure for table `keyphrase_method`
--

CREATE TABLE IF NOT EXISTS `keyphrase_method` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `name` varchar(50) NOT NULL,
  `description` text NOT NULL,
  PRIMARY KEY (`id`),
  KEY `name` (`name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8 AUTO_INCREMENT=1 ;

-- --------------------------------------------------------

--
-- Table structure for table `page`
--

CREATE TABLE IF NOT EXISTS `page` (
  `id` int(10) unsigned NOT NULL AUTO_INCREMENT COMMENT 'Internal page id',
  `fb_page_id` varchar(100) NOT NULL COMMENT 'FB Page ID',
  `fb_page_name` int(11) NOT NULL COMMENT 'FB Page Name',
  `last_updated` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `owner` bigint(20) unsigned NOT NULL COMMENT 'User Instance that owns this page',
  PRIMARY KEY (`id`),
  KEY `owner` (`owner`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8 AUTO_INCREMENT=1 ;

-- --------------------------------------------------------

--
-- Table structure for table `post`
--

CREATE TABLE IF NOT EXISTS `post` (
  `id` int(10) unsigned NOT NULL AUTO_INCREMENT,
  `fb_post_id` varchar(255) NOT NULL,
  `type` varchar(25) NOT NULL,
  `text` text NOT NULL,
  `when` datetime NOT NULL,
  `parent` int(10) unsigned DEFAULT NULL,
  `page` int(10) unsigned NOT NULL,
  `from` bigint(20) unsigned NOT NULL,
  PRIMARY KEY (`id`),
  KEY `fb_post_id` (`fb_post_id`,`parent`,`page`,`from`),
  KEY `parent` (`parent`),
  KEY `from` (`from`),
  KEY `page` (`page`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8 AUTO_INCREMENT=1 ;

-- --------------------------------------------------------

--
-- Table structure for table `post_keyphrase_assoc`
--

CREATE TABLE IF NOT EXISTS `post_keyphrase_assoc` (
  `post_id` int(10) unsigned NOT NULL,
  `keyphrase_id` bigint(20) unsigned NOT NULL,
  PRIMARY KEY (`post_id`,`keyphrase_id`),
  KEY `post_id` (`post_id`),
  KEY `keyphrase_id` (`keyphrase_id`)
) ENGINE=InnoDB DEFAULT CHARSET=latin1;

-- --------------------------------------------------------

--
-- Table structure for table `user`
--

CREATE TABLE IF NOT EXISTS `user` (
  `id` bigint(20) unsigned NOT NULL COMMENT 'FB User ID',
  `fullname` varchar(500) NOT NULL COMMENT 'FB User Fullname',
  `alias` varchar(50) NOT NULL COMMENT 'Project alias for the user instance',
  PRIMARY KEY (`id`),
  KEY `alias` (`alias`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8;

--
-- Constraints for dumped tables
--

--
-- Constraints for table `page`
--
ALTER TABLE `page`
  ADD CONSTRAINT `page_ibfk_1` FOREIGN KEY (`owner`) REFERENCES `user` (`id`) ON DELETE NO ACTION ON UPDATE NO ACTION;

--
-- Constraints for table `post`
--
ALTER TABLE `post`
  ADD CONSTRAINT `post_ibfk_5` FOREIGN KEY (`from`) REFERENCES `user` (`id`) ON UPDATE NO ACTION,
  ADD CONSTRAINT `post_ibfk_1` FOREIGN KEY (`parent`) REFERENCES `post` (`id`) ON DELETE NO ACTION ON UPDATE NO ACTION,
  ADD CONSTRAINT `post_ibfk_2` FOREIGN KEY (`page`) REFERENCES `page` (`id`) ON UPDATE NO ACTION,
  ADD CONSTRAINT `post_ibfk_3` FOREIGN KEY (`parent`) REFERENCES `post` (`id`) ON DELETE NO ACTION ON UPDATE NO ACTION,
  ADD CONSTRAINT `post_ibfk_4` FOREIGN KEY (`page`) REFERENCES `page` (`id`) ON UPDATE NO ACTION;

--
-- Constraints for table `post_keyphrase_assoc`
--
ALTER TABLE `post_keyphrase_assoc`
  ADD CONSTRAINT `post_keyphrase_assoc_ibfk_2` FOREIGN KEY (`keyphrase_id`) REFERENCES `keyphrase` (`id`) ON DELETE NO ACTION ON UPDATE NO ACTION,
  ADD CONSTRAINT `post_keyphrase_assoc_ibfk_1` FOREIGN KEY (`post_id`) REFERENCES `post` (`id`) ON DELETE NO ACTION ON UPDATE NO ACTION;
